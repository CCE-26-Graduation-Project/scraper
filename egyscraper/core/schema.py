"""Canonical product schema shared by every spider in the project.

A single source of truth for the standardized record. The schema is variant
aware: a product carries a ``variants`` list and never collapses variant level
price or stock into a single number. Money is represented as ``Decimal`` so no
precision is lost between extraction and storage.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

# Ordered product level fields. Order is preserved on export so JSON output is
# stable and diff friendly.
SCHEMA_FIELDS: List[str] = [
    "product_id",
    "source",
    "vendor",
    "brand",
    "brand_normalized",
    "title",
    "description",
    "category",
    "subcategory",
    "gender",
    "price",
    "original_price",
    "currency",
    "availability",
    "sku",
    "barcode",
    "gtin",
    "rating",
    "review_count",
    "image_urls",
    "main_image",
    "product_url",
    "material",
    "colors",
    "color_images",
    "sizes",
    "variants",
    "attributes",
    "content_hash",
    "scope",
    "source_updated_at",
    "first_seen",
    "last_seen",
    "scraped_at",
]

# Per variant fields. Each entry in product["variants"] uses exactly these keys.
VARIANT_FIELDS: List[str] = [
    "variant_id",
    "platform_variant_id",
    "sku",
    "barcode",
    "size",
    "color",
    "price",
    "original_price",
    "currency",
    "available",
    "inventory_quantity",
]

# Fields a record cannot be exported without.
REQUIRED_FIELDS: List[str] = [
    "title",
    "price",
    "image_urls",
    "product_url",
]


def empty_product() -> Dict[str, Any]:
    """Return a fresh product record with every field present and defaulted.

    Money fields default to None (never a fabricated zero). Lists and dicts
    default to empty so downstream consumers never hit a missing key.
    """
    return {
        "product_id": "",
        "source": "",
        "vendor": "",
        "brand": "",
        "brand_normalized": "",
        "title": "",
        "description": "",
        "category": "",
        "subcategory": "",
        "gender": "",
        "price": None,            # Decimal once normalized
        "original_price": None,   # Decimal once normalized
        "currency": "EGP",
        "availability": "",
        "sku": None,
        "barcode": None,
        "gtin": None,
        "rating": None,
        "review_count": None,
        "image_urls": [],
        "main_image": "",
        "product_url": "",
        "material": [],
        "colors": [],
        "color_images": {},
        "sizes": [],
        "variants": [],
        "attributes": {},
        "content_hash": "",
        "scope": None,
        "source_updated_at": None,
        "first_seen": None,
        "last_seen": None,
        "scraped_at": "",
    }


def empty_variant() -> Dict[str, Any]:
    """Return a fresh variant record with every field present and defaulted."""
    return {
        "variant_id": "",
        "platform_variant_id": None,
        "sku": None,
        "barcode": None,
        "size": None,
        "color": None,
        "price": None,            # Decimal once normalized
        "original_price": None,   # Decimal once normalized
        "currency": "EGP",
        "available": None,
        "inventory_quantity": None,
    }


def ordered(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return the record with keys in canonical schema order.

    Unknown keys are appended at the end so nothing is lost, but the known
    fields always lead in a stable order.
    """
    out = {field: record.get(field) for field in SCHEMA_FIELDS}
    for key, value in record.items():
        if key not in out:
            out[key] = value
    return out


def missing_required(record: Dict[str, Any]) -> List[str]:
    """Return the list of required fields that are empty or absent.

    A price of Decimal(0) counts as present; only None, empty string and empty
    list are treated as missing.
    """
    missing = []
    for field in REQUIRED_FIELDS:
        value = record.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    return missing
