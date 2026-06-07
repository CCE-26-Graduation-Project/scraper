"""Map a Shopify ``products.json`` product into the variant aware schema.

The mapper preserves every variant rather than collapsing the product to a
single price. Each variant keeps its own sku, barcode, size, colour, price,
availability and stock. Product level fields are roll ups derived from the
variants (lowest price, any available), and identifiers are captured at both
levels for cross store matching.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from w3lib.html import remove_tags, replace_entities

from . import normalize
from .ids import product_id, variant_id
from .schema import empty_product, empty_variant


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(html: Optional[str]) -> str:
    if not html:
        return ""
    return " ".join(replace_entities(remove_tags(html)).split()).strip()


def _tags_list(raw_tags: Any) -> List[str]:
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    if isinstance(raw_tags, str):
        return [t.strip() for t in raw_tags.split(",") if t.strip()]
    return []


def _option_names(product: Dict[str, Any]) -> List[str]:
    """Return option names in order (option1, option2, option3 map to these)."""
    return [str(o.get("name", "")).strip().lower() for o in (product.get("options") or [])]


def _looks_like_gtin(barcode: Optional[str]) -> bool:
    return bool(barcode) and str(barcode).isdigit() and len(str(barcode)) in (8, 12, 13, 14)


def _build_variants(product: Dict[str, Any], pid: str) -> List[Dict[str, Any]]:
    """Build the full variant list, preserving per variant data."""
    option_names = _option_names(product)
    variants: List[Dict[str, Any]] = []

    for index, raw in enumerate(product.get("variants", []) or []):
        # Recover size and colour from the positional option values.
        size = color = None
        option_values = [raw.get("option1"), raw.get("option2"), raw.get("option3")]
        for name, value in zip(option_names, option_values):
            if not value:
                continue
            if name in ("size", "المقاس", "مقاس"):
                size = str(value).strip()
            elif name in ("color", "colour", "اللون", "لون"):
                color = str(value).strip()

        barcode = (raw.get("barcode") or None)
        sku = (raw.get("sku") or None)

        variant = empty_variant()
        variant.update(
            {
                "variant_id": variant_id(
                    pid, barcode=barcode, sku=sku,
                    platform_variant_id=raw.get("id"),
                    size=size, color=color, index=index,
                ),
                "platform_variant_id": raw.get("id"),
                "sku": sku,
                "barcode": barcode,
                "size": size,
                "color": color,
                "price": normalize.to_decimal(raw.get("price")),
                "original_price": normalize.to_decimal(raw.get("compare_at_price")),
                "currency": "EGP",
                "available": raw.get("available"),
                # Public products.json rarely exposes stock counts; keep null
                # rather than inventing a number.
                "inventory_quantity": raw.get("inventory_quantity"),
            }
        )
        # An original price that is not actually higher is meaningless.
        if (
            variant["price"] is not None
            and variant["original_price"] is not None
            and variant["original_price"] <= variant["price"]
        ):
            variant["original_price"] = None
        variants.append(variant)

    return variants


def _rollup_identifier(variants: List[Dict[str, Any]], key: str) -> Optional[str]:
    """Return a product level identifier only when it is unambiguous.

    A single variant lends its identifier to the product; multiple variants
    have multiple codes, so the product level value stays null and the truth
    lives on each variant.
    """
    values = {v.get(key) for v in variants if v.get(key)}
    return next(iter(values)) if len(values) == 1 else None


def map_shopify_product(
    product: Dict[str, Any],
    base_url: str,
    source: str,
    currency: str = "EGP",
) -> Dict[str, Any]:
    """Convert one Shopify product object into the standardized record."""
    record = empty_product()

    handle = product.get("handle", "")
    platform_id = product.get("id")
    url = f"{base_url.rstrip('/')}/products/{handle}" if handle else base_url
    pid = product_id(source, platform_product_id=platform_id, handle=handle, product_url=url)

    tags = _tags_list(product.get("tags"))
    product_type = product.get("product_type") or ""
    title = (product.get("title") or "").strip()
    description = _clean_text(product.get("body_html"))
    tag_text = " ".join(tags)

    variants = _build_variants(product, pid)

    # Roll ups derived from variants (never a collapse: variants are kept).
    variant_prices = [v["price"] for v in variants if v["price"] is not None]
    compare_prices = [v["original_price"] for v in variants if v["original_price"] is not None]
    price: Optional[Decimal] = min(variant_prices) if variant_prices else None
    original: Optional[Decimal] = max(compare_prices) if compare_prices else None
    if price is not None and original is not None and original <= price:
        original = None

    in_stock = any(v.get("available") for v in variants)

    images = normalize.clean_list(
        img.get("src") for img in (product.get("images") or [])
        if isinstance(img, dict) and img.get("src")
    )

    colors = normalize.normalize_colors(v.get("color") for v in variants)
    sizes = normalize.clean_list(v.get("size") for v in variants)

    product_barcode = _rollup_identifier(variants, "barcode")
    product_sku = _rollup_identifier(variants, "sku")
    vendor = (product.get("vendor") or "").strip()

    record.update(
        {
            "product_id": pid,
            "source": source,
            "vendor": vendor,
            "brand": vendor,
            "brand_normalized": vendor.lower(),
            "title": title,
            "description": description,
            "category": normalize.normalize_category(product_type, tag_text, title),
            "subcategory": product_type.strip(),
            "gender": normalize.normalize_gender(product_type, tag_text, title, handle),
            "price": price,
            "original_price": original,
            "currency": currency,
            "availability": normalize.normalize_availability(in_stock),
            "sku": product_sku,
            "barcode": product_barcode,
            "gtin": product_barcode if _looks_like_gtin(product_barcode) else None,
            "rating": None,
            "review_count": None,
            "image_urls": images,
            "main_image": images[0] if images else "",
            "product_url": url,
            "material": normalize.extract_materials(tag_text, description, title),
            "colors": colors,
            "sizes": sizes,
            "variants": variants,
            "attributes": {
                "platform": "shopify",
                "platform_product_id": platform_id,
                "handle": handle,
                "product_type": product_type,
                "tags": tags,
                "variant_count": len(variants),
            },
            "source_updated_at": product.get("updated_at"),
            "scraped_at": _now_iso(),
        }
    )
    return record
