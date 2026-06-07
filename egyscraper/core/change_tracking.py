"""Incremental crawl foundation.

This module provides the building blocks a future incremental crawler needs,
without implementing any scheduling. Three concerns:

  content_hash   a stable fingerprint of the fields that matter for retrieval
                 and pricing, used to tell whether a product actually changed.
  detect_changes diff a set of freshly scraped records against the last known
                 state, classifying each as new, updated, unchanged or removed.
  CrawlState     a small JSON backed store of per product hashes, last seen
                 timestamps, and a per store high water mark, so a later run
                 can fetch only what changed.

Scheduling, triggering, and delta requests to stores are deliberately left for
a later phase; this is the data layer they will stand on.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

# Fields whose change should invalidate an embedding or a stored row. Price and
# availability changes matter for comparison; title, description and images
# matter for embeddings; variants capture per size price and stock.
_CONTENT_FIELDS = [
    "title", "description", "category", "gender", "brand",
    "price", "original_price", "availability", "image_urls",
]


def _stable(value: Any) -> Any:
    """Coerce values into a JSON stable form (Decimal to string, sets sorted)."""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    if isinstance(value, dict):
        return {k: _stable(value[k]) for k in sorted(value)}
    return value


def content_hash(record: Dict[str, Any]) -> str:
    """Return a SHA256 fingerprint of a product's retrieval relevant content.

    Two crawls of an unchanged product yield the same hash; a price drop, a
    stock flip, a new image or an edited title yields a different one. Variant
    skus, prices and availability are folded in so per size changes are caught.
    """
    payload: Dict[str, Any] = {f: _stable(record.get(f)) for f in _CONTENT_FIELDS}
    payload["variants"] = [
        {
            "sku": v.get("sku"),
            "price": _stable(v.get("price")),
            "available": v.get("available"),
        }
        for v in (record.get("variants") or [])
    ]
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ChangeSet:
    new: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, int]:
        return {
            "new": len(self.new),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
        }


def detect_changes(
    previous: Dict[str, str],
    current_records: List[Dict[str, Any]],
) -> ChangeSet:
    """Classify current records against a previous {product_id: content_hash}.

    ``removed`` lists products present last time but absent now (candidates for
    marking out of stock or delisted, decided by the caller).
    """
    changes = ChangeSet()
    seen = set()
    for record in current_records:
        pid = record.get("product_id")
        if not pid:
            continue
        seen.add(pid)
        h = record.get("content_hash") or content_hash(record)
        if pid not in previous:
            changes.new.append(pid)
        elif previous[pid] != h:
            changes.updated.append(pid)
        else:
            changes.unchanged.append(pid)
    changes.removed = [pid for pid in previous if pid not in seen]
    return changes


@dataclass
class CrawlState:
    """Per store crawl state persisted as JSON.

    Stores, for each product, its last content hash and last seen timestamp,
    plus a high water mark of the newest source update observed. A later
    incremental crawl reads this to request only products changed since.
    """

    store: str
    products: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    updated_at_max: Optional[str] = None

    @classmethod
    def load(cls, path: str, store: str) -> "CrawlState":
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                return cls(
                    store=data.get("store", store),
                    products=data.get("products", {}),
                    updated_at_max=data.get("updated_at_max"),
                )
            except (ValueError, OSError):
                pass
        return cls(store=store)

    def hashes(self) -> Dict[str, str]:
        return {pid: meta.get("content_hash", "") for pid, meta in self.products.items()}

    def update_from(self, records: List[Dict[str, Any]]) -> ChangeSet:
        """Apply a batch of freshly scraped records and return the change set."""
        changes = detect_changes(self.hashes(), records)
        for record in records:
            pid = record.get("product_id")
            if not pid:
                continue
            self.products[pid] = {
                "content_hash": record.get("content_hash") or content_hash(record),
                "last_seen": record.get("last_seen") or record.get("scraped_at"),
            }
            src_updated = record.get("source_updated_at")
            if src_updated and (self.updated_at_max is None or src_updated > self.updated_at_max):
                self.updated_at_max = src_updated
        return changes

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "store": self.store,
                    "updated_at_max": self.updated_at_max,
                    "products": self.products,
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
