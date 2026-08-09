"""Top-level pipeline orchestrator.

Runs every scraper this project has — Shopify stores (via egyscraper),
JSON-LD stores, and marketplaces — then loads every product JSON file from
the shared Products/ folder into the database via a delta: only rows whose
content actually changed are touched (new rows inserted, changed rows
re-embedded and re-inserted, vanished rows deleted).

One scraper failing does not abort the pipeline; each step is fault
isolated and the run continues, matching egyscraper's own philosophy.

Usage
-----
    python orchestrator.py                        # scrape everything, then load
    python orchestrator.py --skip-scrape           # load only, use existing Products/
    python orchestrator.py --skip-load             # scrape only, no DB insert
    python orchestrator.py --skip-jsonld           # skip decathlon/lcwaikiki/etc
    python orchestrator.py --skip-marketplaces     # skip jumia/noon
    python orchestrator.py --shopify-args "--parallel 5"

Note: the JSON-LD stores include a few (lacoste, adidas, newbalance, defacto)
that are currently blocked by anti-bot measures (see brands.md) — they will
run, fail fast or slow depending on the store, and contribute nothing, which
is expected until those are unblocked or given a different extraction path.
decathlon alone can take well over an hour (it crawls one product page per
request, no bulk listing endpoint) — use --skip-jsonld for a quick run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Windows consoles default stdout/stderr to the system codepage (cp1252),
# which cannot encode the em dashes used in this file's help text and
# section banners.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
PRODUCTS_DIR = ROOT / "Products"


def _run(cmd: list[str], label: str) -> None:
    """Run a subprocess to completion; log but never raise on failure so one
    bad store/spider can't take down the rest of the pipeline."""
    print(f"\n  -> {label}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"     {label} exited with code {result.returncode} (continuing)")


def run_shopify(extra_args: list[str]) -> None:
    print("\n" + "=" * 48)
    print("  Shopify stores (egyscraper)")
    print("=" * 48)
    _run(
        [sys.executable, "-m", "egyscraper.run", "--all"] + extra_args,
        "egyscraper --all",
    )


def run_jsonld() -> None:
    from egyscraper.stores.jsonld_stores import all_slugs  # noqa: PLC0415

    print("\n" + "=" * 48)
    print("  JSON-LD stores")
    print("=" * 48)
    for slug in all_slugs():
        _run(
            [sys.executable, "-m", "scrapy", "crawl", "jsonld",
             "-a", f"store={slug}", "-s", "LOG_LEVEL=WARNING"],
            slug,
        )


def run_marketplaces() -> None:
    print("\n" + "=" * 48)
    print("  Marketplaces")
    print("=" * 48)
    for name in ("jumia", "noon"):
        _run(
            [sys.executable, "-m", "scrapy", "crawl", name, "-s", "LOG_LEVEL=WARNING"],
            name,
        )


def load_products() -> None:
    print("\n" + "=" * 48)
    print("  Loading Products/ -> database (delta mode)")
    print("=" * 48)
    import json as _json
    sys.path.insert(0, str(ROOT))
    from load_products import (  # noqa: PLC0415
        generate_product_hash,
        fetch_db_products,
        delete_db_products,
        insert_products_to_db,
    )
    from delta_calculator import calculate_delta  # noqa: PLC0415

    json_files = sorted(PRODUCTS_DIR.glob("*.json"))
    if not json_files:
        print("No product files found in Products/.")
        return

    # 1. Read every scraped product; build per-color delta records.
    #    _id = "product_url||color" so the delta operates at (product, color)
    #    granularity. The hash uses the same per-colour image resolution as
    #    insert_products_to_db (colour-specific image when available, else
    #    the product's main image) so a colour-only image change is actually
    #    detected instead of being masked by always hashing the main image.
    file_products: dict = {}
    all_new: list = []
    for jf in json_files:
        with open(jf, encoding="utf-8") as f:
            products = _json.load(f)
        file_products[jf] = products
        for p in products:
            if not p.get("product_url"):
                continue
            images = p.get("image_urls") or []
            color_images_map = p.get("color_images") or {}
            title = (p.get("title") or "").strip()
            price = p.get("price", 0)
            for color in (p.get("colors") or [""]):
                color_img_list = (color_images_map.get(color) or []) if color else []
                image = color_img_list[0] if color_img_list else (images[0] if images else "")
                all_new.append({
                    "_id": f"{p['product_url']}||{color or ''}",
                    "data_hash": generate_product_hash(title, price, image, color or None),
                })

    # 2. Fetch current DB state (also per product_url+color).
    print("Fetching existing products from DB...")
    old_data = fetch_db_products()
    print(f"  {len(old_data)} existing product-color rows in DB.")

    # 3. Compute delta.
    delta = calculate_delta(old_data, all_new, id_key="_id", hash_key="data_hash")
    print(
        f"  Delta — new: {len(delta['new'])}, "
        f"updated: {len(delta['updated'])}, "
        f"deleted: {len(delta['deleted'])}."
    )

    # 4. Remove updated + deleted rows from DB.
    to_delete = [item["_id"] for item in delta["updated"] + delta["deleted"]]
    if to_delete:
        print(f"Removing {len(to_delete)} product-color rows from DB...")
        delete_db_products(to_delete)

    # 5. Insert new + updated rows, file by file (preserves checkpointing).
    #    Build a {product_url -> {colors}} map so we only insert the affected colors.
    to_insert: dict = {}
    for item in delta["new"] + delta["updated"]:
        url, _, color = item["_id"].partition("||")
        to_insert.setdefault(url, set()).add(color)

    if not to_insert:
        print("Nothing to insert.")
        return

    print(f"Inserting {sum(len(v) for v in to_insert.values())} product-color rows...")
    for jf, products in file_products.items():
        filtered = []
        for p in products:
            url = p.get("product_url")
            if url not in to_insert:
                continue
            needed = to_insert[url]
            matching_colors = [c for c in (p.get("colors") or [""]) if (c or "") in needed]
            if matching_colors:
                p_copy = dict(p)
                p_copy["colors"] = matching_colors
                filtered.append(p_copy)
        if not filtered:
            continue
        print(f"\nProcessing {jf.name} ({len(filtered)} products)...")
        stopped = insert_products_to_db(jf, products=filtered)
        if stopped:
            print("Stopped due to repeated Modal failures.")
            break


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end scraper + DB-load pipeline."
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="skip all scraping, load whatever is already in Products/",
    )
    parser.add_argument(
        "--skip-jsonld",
        action="store_true",
        help="skip the JSON-LD stores (decathlon, lcwaikiki, etc.) — decathlon "
             "alone can take well over an hour",
    )
    parser.add_argument(
        "--skip-marketplaces",
        action="store_true",
        help="skip jumia/noon",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="scrape but do not load results into the database",
    )
    parser.add_argument(
        "--shopify-args",
        default="",
        metavar="ARGS",
        help='extra args forwarded to egyscraper.run (e.g. "--parallel 5")',
    )
    args = parser.parse_args()

    PRODUCTS_DIR.mkdir(exist_ok=True)

    if not args.skip_scrape:
        extra = args.shopify_args.split() if args.shopify_args else []
        run_shopify(extra)
        if not args.skip_jsonld:
            run_jsonld()
        if not args.skip_marketplaces:
            run_marketplaces()

    if not args.skip_load:
        load_products()

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
