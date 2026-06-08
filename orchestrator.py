"""Top-level pipeline orchestrator.

Runs every scraper in sequence, then loads all collected product JSON files
from the shared Products/ folder into the database via load_products.

Usage
-----
    python orchestrator.py                  # full pipeline
    python orchestrator.py --shopify-only   # skip egyscraper
    python orchestrator.py --skip-load      # scrape only, no DB insert
    python orchestrator.py --egyscraper-args "--parallel 3 --all"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHOPIFY_DIR = ROOT / "Shopify"
PRODUCTS_DIR = ROOT / "Products"


def run_shopify() -> None:
    print("\n" + "=" * 48)
    print("  Shopify scraper")
    print("=" * 48)
    subprocess.run(
        [sys.executable, "orchestrator.py"],
        cwd=SHOPIFY_DIR,
        check=True,
    )


def run_egyscraper(extra_args: list[str]) -> None:
    print("\n" + "=" * 48)
    print("  egyscraper")
    print("=" * 48)
    subprocess.run(
        [sys.executable, "-m", "egyscraper.run", "--all"] + extra_args,
        cwd=ROOT,
        check=True,
    )



def load_products() -> None:
    print("\n" + "=" * 48)
    print("  Loading Products/ → database (delta mode)")
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
    #    _id = "product_url||color" so the delta operates at (product, color) granularity.
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
            first_image = images[0] if images else ""
            title = (p.get("title") or "").strip()
            price = p.get("price", 0)
            for color in (p.get("colors") or [""]):
                all_new.append({
                    "_id": f"{p['product_url']}||{color or ''}",
                    "data_hash": generate_product_hash(title, price, first_image, color or None),
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
        "--shopify-only",
        action="store_true",
        help="run only the Shopify scraper, skip egyscraper",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="scrape but do not load results into the database",
    )
    parser.add_argument(
        "--egyscraper-args",
        default="",
        metavar="ARGS",
        help='extra args forwarded to egyscraper.run (e.g. "--parallel 3")',
    )
    args = parser.parse_args()

    PRODUCTS_DIR.mkdir(exist_ok=True)

    run_shopify()

    if not args.shopify_only:
        extra = args.egyscraper_args.split() if args.egyscraper_args else []
        run_egyscraper(extra)

    if not args.skip_load:
        load_products()

    print("\nPipeline complete.")


if __name__ == "__main__":
    main()
