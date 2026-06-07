"""Map a Noon catalog API hit dict to the egyscraper product schema.

Evidence basis:
  HAR www.noon.com.har, catalog API response for men-31225 category.
  Observed hit fields:
    offer_code, catalog_sku, sku, sku_config, brand, name,
    plp_specifications {k: v}, price (int), sale_price (float),
    url (slug only, e.g. "men-s-mason-round-..."),
    image_key, image_url, image_keys[], image_urls[],
    is_buyable (bool), product_rating {best_rating, count, value},
    flags[], store_name, best_seller_rank, nudges[], brand_code,
    estimated_delivery_date, groups[], assets

  Product page JSON-LD (for cross-reference):
    sku: "ZA9B82B9F9D8AC3FB19A6Z", price: "365.00", priceCurrency: "EGP",
    image[]: [f.nooncdn.com/p/pzsku/{sku}/45/_/{ts}/{uuid}.jpg],
    offers[].url: "/egypt-en/{slug}/{sku}/p/"
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from egyscraper.core import normalize
from egyscraper.core.ids import product_id
from egyscraper.core.schema import empty_product

_BASE_URL = "https://www.noon.com"
_PRODUCT_URL_TEMPLATE = "{base}/egypt-en/{slug}/{sku}/p/"


def _noon_price(raw: Any) -> Optional[Decimal]:
    """Convert int/float/str price to Decimal."""
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _build_product_url(hit: Dict) -> str:
    slug = hit.get("url") or ""
    sku = hit.get("sku") or hit.get("catalog_sku") or ""
    return _PRODUCT_URL_TEMPLATE.format(base=_BASE_URL, slug=slug, sku=sku)


def _image_urls(hit: Dict) -> List[str]:
    urls = hit.get("image_urls")
    if isinstance(urls, list) and urls:
        return [str(u) for u in urls if u]
    single = hit.get("image_url")
    if single:
        return [str(single)]
    return []


def map_noon_hit(hit: Dict[str, Any], source: str = "www.noon.com") -> Optional[Dict]:
    """Return a product record dict from a Noon catalog API hit, or None."""
    sku = str(hit.get("sku") or hit.get("catalog_sku") or "").strip()
    if not sku:
        return None

    title = str(hit.get("name") or "").strip()
    if not title:
        return None

    brand = str(hit.get("brand") or "").strip()
    images = _image_urls(hit)
    product_url = _build_product_url(hit)

    price = _noon_price(hit.get("sale_price") or hit.get("price"))
    original_price = _noon_price(hit.get("price")) if hit.get("sale_price") else None

    rating_data = hit.get("product_rating") or {}
    rating = normalize.to_decimal(rating_data.get("value"))
    review_count_raw = rating_data.get("count")
    try:
        review_count = int(review_count_raw) if review_count_raw is not None else None
    except (TypeError, ValueError):
        review_count = None

    # plp_specifications carry attribute-style data but no category signal.
    plp_specs: Dict[str, Any] = hit.get("plp_specifications") or {}

    pid = product_id(source, platform_product_id=sku, product_url=product_url)

    record = empty_product()
    record.update(
        {
            "product_id": pid,
            "source": source,
            "vendor": brand,
            "brand": brand,
            "brand_normalized": brand.lower(),
            "title": title,
            "description": "",
            "category": normalize.normalize_category(title),
            "subcategory": "",
            "gender": normalize.normalize_gender(title),
            "price": price,
            "original_price": original_price,
            "currency": "EGP",
            "availability": "in_stock" if hit.get("is_buyable") else "out_of_stock",
            "sku": sku,
            "barcode": None,
            "gtin": None,
            "rating": rating,
            "review_count": review_count,
            "image_urls": images,
            "main_image": images[0] if images else "",
            "product_url": product_url,
            "material": [],
            "colors": [],
            "sizes": [],
            "variants": [],
            "attributes": {
                "platform": "noon_catalog_api",
                "offer_code": hit.get("offer_code"),
                "sku_config": hit.get("sku_config"),
                "store_name": hit.get("store_name"),
                "flags": hit.get("flags") or [],
                "plp_specifications": plp_specs,
                "is_bestseller": hit.get("is_bestseller"),
            },
        }
    )
    return record
