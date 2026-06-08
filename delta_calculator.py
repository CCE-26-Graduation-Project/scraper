"""Delta calculator for the incremental scraper pipeline.

Compares two snapshots of a product catalog and isolates exactly which records
are new, updated, or deleted — so embeddings and DB writes are limited to the
records that actually changed.

This module is intentionally free of any database or embedding logic; it is
purely a data-diffing utility that downstream pipeline stages consume.
"""

from __future__ import annotations

from typing import Any


def calculate_delta(
    old_data: list[dict[str, Any]],
    new_data: list[dict[str, Any]],
    *,
    id_key: str = "product_id",
    hash_key: str = "data_hash",
) -> dict[str, list[dict[str, Any]]]:
    """Compare two product snapshots and return a three-way delta.

    Both lists must contain dicts with a stable unique identifier (``id_key``)
    and a pre-computed content hash (``hash_key``) that fingerprints the fields
    relevant to embeddings and DB rows (title, images, price, etc.).

    Records missing the identifier field are silently skipped — they cannot be
    tracked across runs. Records whose hash field is absent are treated as an
    empty string so they reliably surface as ``updated`` rather than being
    silently ignored.

    Time complexity: O(N + M) where N = |old_data| and M = |new_data|.
    No nested loops; all membership tests are O(1) dict/set lookups.

    Args:
        old_data:  Products currently stored in the database (previous state).
        new_data:  Products returned by the latest scrape run (current state).
        id_key:    Field used as the unique product identifier.
                   Defaults to ``"product_id"``; pass ``"product_url"`` for
                   URL-keyed stores where no surrogate key exists yet.
        hash_key:  Field carrying the pre-computed content hash.
                   Defaults to ``"data_hash"``; use ``"content_hash"`` if the
                   records were produced by ``egyscraper.core.change_tracking``.

    Returns:
        A plain dict with three keys, each mapping to a list of full records:

        ``"new"``
            Products present in *new_data* but absent from *old_data*.
            Require a fresh DB insert and a new embedding.

        ``"updated"``
            Products present in both snapshots but whose hash changed.
            Require a DB update and a recomputed embedding.

        ``"deleted"``
            Products present in *old_data* but absent from *new_data*.
            Require removal from the DB or an out-of-stock mark, and vector
            deletion from the embedding store.
    """
    # Build a single id→record index from the old snapshot so every subsequent
    # lookup is O(1).  Dict comprehension preserves only the last record when
    # duplicates exist (same behaviour as the DB upsert that wrote old_data).
    old_lookup: dict[str, dict[str, Any]] = {
        record[id_key]: record
        for record in old_data
        if record.get(id_key)
    }

    new_products: list[dict[str, Any]] = []
    updated_products: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in new_data:
        pid = record.get(id_key)
        if not pid:
            continue
        seen_ids.add(pid)

        if pid not in old_lookup:
            new_products.append(record)
        elif old_lookup[pid].get(hash_key, "") != record.get(hash_key, ""):
            updated_products.append(record)
        # else: hash identical → unchanged, skip entirely

    # Every id that was in old_lookup but never appeared in new_data is deleted.
    deleted_products: list[dict[str, Any]] = [
        record
        for pid, record in old_lookup.items()
        if pid not in seen_ids
    ]

    return {
        "new": new_products,
        "updated": updated_products,
        "deleted": deleted_products,
    }


# ---------------------------------------------------------------------------
# Self-contained smoke test — run this file directly to verify correctness.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Fixtures: four products across two scrape runs.
    #
    #  prod-1  unchanged  (same hash in both snapshots)
    #  prod-2  updated    (price changed → different hash)
    #  prod-3  deleted    (present in old, absent from new)
    #  prod-4  new        (absent from old, present in new)

    OLD: list[dict] = [
        {"product_id": "prod-1", "title": "Blue Jeans",    "data_hash": "aaa111"},
        {"product_id": "prod-2", "title": "Red Sneakers",  "data_hash": "bbb222"},
        {"product_id": "prod-3", "title": "Green Hoodie",  "data_hash": "ccc333"},
    ]

    NEW: list[dict] = [
        {"product_id": "prod-1", "title": "Blue Jeans",    "data_hash": "aaa111"},  # unchanged
        {"product_id": "prod-2", "title": "Red Sneakers",  "data_hash": "bbb999"},  # hash changed
        # prod-3 is gone
        {"product_id": "prod-4", "title": "White T-Shirt", "data_hash": "ddd444"},  # brand new
    ]

    delta = calculate_delta(OLD, NEW)

    def ids(lst: list[dict]) -> list[str]:
        return [r["product_id"] for r in lst]

    assert ids(delta["new"])     == ["prod-4"],            f"new mismatch:     {delta['new']}"
    assert ids(delta["updated"]) == ["prod-2"],            f"updated mismatch: {delta['updated']}"
    assert ids(delta["deleted"]) == ["prod-3"],            f"deleted mismatch: {delta['deleted']}"

    # Verify unchanged product is absent from all three lists.
    all_changed = (
        delta["new"] + delta["updated"] + delta["deleted"]
    )
    assert not any(r["product_id"] == "prod-1" for r in all_changed), \
        "unchanged product leaked into delta output"

    print("All assertions passed.")
    print(f"  new:     {ids(delta['new'])}")
    print(f"  updated: {ids(delta['updated'])}")
    print(f"  deleted: {ids(delta['deleted'])}")
