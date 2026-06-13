"""sync_products.py — incremental product sync pipeline.

Steps
-----
1. Read all products from the DB → db_snapshot.json
2. Load all scraped products from Products/ → scraped_snapshot.json
3. Expand each scraped product into per-(url, color) entries and compute
   data_hash using the same function that was used when the row was first
   inserted (generate_product_hash from load_products).  This ensures the
   hashes are comparable with what is already stored in the DB.
4. Run calculate_delta to find new / updated / deleted rows.
5. Delete updated AND deleted rows from the DB.
6. Insert new + updated products via insert_products_to_db.

Usage
-----
    python sync_products.py              # full sync
    python sync_products.py --dry-run   # compute delta, print counts, no writes
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from delta_calculator import calculate_delta
from load_products import (
    delete_db_products,
    fetch_db_products,
    generate_product_hash,
    insert_products_to_db,
)

PRODUCTS_DIR = Path(__file__).resolve().parent / "Products"
DB_SNAPSHOT = Path(__file__).resolve().parent / "db_snapshot.json"
SCRAPED_SNAPSHOT = Path(__file__).resolve().parent / "scraped_snapshot.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_scraped_products() -> list[dict[str, Any]]:
    """Merge all JSON files from Products/ into a single list."""
    products: list[dict[str, Any]] = []
    for json_file in sorted(PRODUCTS_DIR.glob("*.json")):
        with open(json_file, encoding="utf-8") as f:
            batch = json.load(f)
        if isinstance(batch, list):
            products.extend(batch)
    return products


def to_color_entries(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand each product into one entry per (product_url, color).

    The ``data_hash`` is computed with ``generate_product_hash`` so it is
    directly comparable to the hashes already stored in the DB.  The ``_url``
    field is a back-reference used later to look up the full product object
    when we need to pass it to ``insert_products_to_db``.
    """
    entries: list[dict[str, Any]] = []
    for product in products:
        url = product.get("product_url")
        if not url:
            continue
        title = (product.get("title") or "").strip()
        price = product.get("price", 0)
        images = product.get("image_urls") or []
        image_url = images[0] if images else ""
        colors = product.get("colors") or [""]

        for color in colors:
            entries.append(
                {
                    "_id": f"{url}||{color or ''}",
                    "data_hash": generate_product_hash(
                        title, price, image_url, color or None
                    ),
                    "_url": url,
                }
            )
    return entries


def group_by_source(
    products: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        source = p.get("source", "unknown")
        result.setdefault(source, []).append(p)
    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_sync(dry_run: bool = False) -> None:
    # 1. DB snapshot ----------------------------------------------------------
    print("Fetching DB products...")
    db_products = fetch_db_products()
    DB_SNAPSHOT.write_text(
        json.dumps(db_products, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  {len(db_products)} rows saved → {DB_SNAPSHOT.name}")

    # 2. Scraped snapshot ------------------------------------------------------
    print("Loading scraped products...")
    scraped = load_scraped_products()
    SCRAPED_SNAPSHOT.write_text(
        json.dumps(scraped, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  {len(scraped)} products saved → {SCRAPED_SNAPSHOT.name}")

    # 3. Per-color entries with data_hash -------------------------------------
    scraped_entries = to_color_entries(scraped)
    print(f"  {len(scraped_entries)} (product, color) entries after expansion")

    # 4. Delta ----------------------------------------------------------------
    print("Calculating delta...")
    delta = calculate_delta(
        db_products, scraped_entries, id_key="_id", hash_key="data_hash"
    )
    n_new = len(delta["new"])
    n_upd = len(delta["updated"])
    n_del = len(delta["deleted"])
    print(f"  new: {n_new}  updated: {n_upd}  deleted: {n_del}")

    if dry_run:
        print("Dry run — skipping all DB writes.")
        return

    # 5. Delete updated + deleted rows ----------------------------------------
    ids_to_delete = (
        [e["_id"] for e in delta["updated"]]
        + [e["_id"] for e in delta["deleted"]]
    )
    if ids_to_delete:
        print(f"Deleting {len(ids_to_delete)} rows ({n_upd} updated, {n_del} deleted)...")
        delete_db_products(ids_to_delete)

    # 6. Insert new + updated products ----------------------------------------
    to_insert_entries = delta["new"] + delta["updated"]
    if not to_insert_entries:
        print("Nothing to insert.")
        return

    url_to_product = {
        p["product_url"]: p for p in scraped if p.get("product_url")
    }
    urls_needed = {e["_url"] for e in to_insert_entries}
    products_to_insert = [
        url_to_product[u] for u in urls_needed if u in url_to_product
    ]

    allowed_color_ids = {e["_id"] for e in to_insert_entries}

    print(
        f"Inserting {len(products_to_insert)} products "
        f"({n_new} new, {n_upd} updated)..."
    )
    for source, products in group_by_source(products_to_insert).items():
        json_path = PRODUCTS_DIR / f"{source}_products.json"
        print(f"  [{source}] {len(products)} products")
        stopped = insert_products_to_db(
            str(json_path), products=products, allowed_color_ids=allowed_color_ids
        )
        if stopped:
            print(f"  Stopped early for '{source}' due to repeated API failures.")
            break

    print("Sync complete.")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Incremental product sync")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print the delta but skip all DB writes",
    )
    args = parser.parse_args()
    run_sync(dry_run=args.dry_run)
