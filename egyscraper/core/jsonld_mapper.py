"""Map a schema.org JSON LD Product node into the standardized schema.

Many custom stores (not Shopify) embed a schema.org Product block in each
product page. Reading that structured payload is far more reliable than
scraping rendered HTML, so it is the preferred source for those stores. This
mapper is pure and testable: it takes a parsed JSON LD node plus the page url
and returns a standardized record.

JSON LD is less uniform than Shopify's products.json, so this maps what is
present and leaves the rest null rather than inventing values.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from w3lib.html import remove_tags, replace_entities

from . import normalize
from .ids import product_id, variant_id
from .schema import empty_product, empty_variant


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(replace_entities(remove_tags(str(value))).split()).strip()


def _images(value: Any) -> List[str]:
    """schema.org image may be a string, a list, or an ImageObject.

    Handles:
      - string URL
      - list of string URLs or ImageObject dicts
      - single ImageObject with url, contentUrl (Jumia), or thumbnailUrl
    JSON-LD is embedded in HTML so HTML entities are decoded.
    """
    out: List[str] = []
    if isinstance(value, str):
        out = [value]
    elif isinstance(value, list):
        for v in value:
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, dict):
                # contentUrl may be a list (Jumia ImageObject pattern)
                cu = v.get("contentUrl")
                if isinstance(cu, list):
                    out.extend(str(u) for u in cu if u)
                elif cu:
                    out.append(str(cu))
                elif v.get("url"):
                    out.append(str(v["url"]))
    elif isinstance(value, dict):
        cu = value.get("contentUrl")
        if isinstance(cu, list):
            out.extend(str(u) for u in cu if u)
        elif cu:
            out.append(str(cu))
        elif value.get("url"):
            out.append(str(value["url"]))
    return normalize.clean_list(replace_entities(u) for u in out)


def _brand(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name", "")).strip()
    return str(value or "").strip()


def _availability(text: Optional[str]) -> str:
    if not text:
        return ""
    t = str(text).lower().replace(" ", "").replace("-", "").replace("_", "")
    if "instock" in t:
        return "in_stock"
    if "outofstock" in t or "soldout" in t or "discontinued" in t:
        return "out_of_stock"
    if "preorder" in t or "preorderaction" in t:
        return "preorder"
    return ""


def _gtin(node: Dict[str, Any]) -> Optional[str]:
    for key in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin"):
        if node.get(key):
            return str(node[key])
    return None


def _offer_list(offers: Any) -> List[Dict[str, Any]]:
    """Return offers as a flat list of dicts, whatever shape they arrive in."""
    if offers is None:
        return []
    if isinstance(offers, list):
        return [o for o in offers if isinstance(o, dict)]
    if isinstance(offers, dict):
        return [offers]
    return []


def _price_and_currency(offers_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive a representative price, currency and availability from offers.

    Handles a single Offer, an AggregateOffer (lowPrice/highPrice), or a list.
    """
    prices: List = []
    currency = None
    availability = ""
    for offer in offers_list:
        currency = currency or offer.get("priceCurrency")
        availability = availability or _availability(offer.get("availability"))
        for key in ("price", "lowPrice"):
            p = normalize.to_decimal(offer.get(key))
            if p is not None:
                prices.append(p)
    return {
        "price": min(prices) if prices else None,
        "currency": currency,
        "availability": availability,
    }


def _rating(node: Dict[str, Any]):
    agg = node.get("aggregateRating")
    if not isinstance(agg, dict):
        return None, None
    rating = normalize.to_decimal(agg.get("ratingValue"))
    rc = agg.get("reviewCount") or agg.get("ratingCount")
    review_count = int(rc) if str(rc).isdigit() else None
    return rating, review_count


def _map_product_group(
    node: Dict[str, Any], product_url: str, source: str, currency: str
) -> Dict[str, Any]:
    """Map a schema.org ProductGroup (variesBy colour/size) into one record
    with a populated variants list. Reusable for any ProductGroup store."""
    record = empty_product()

    title = _text(node.get("name"))
    description = _text(node.get("description"))
    brand = _brand(node.get("brand"))
    group_id = node.get("productGroupID") or node.get("productID")
    rating, review_count = _rating(node)

    pid = product_id(source, platform_product_id=group_id, product_url=product_url)

    variant_nodes = [v for v in (node.get("hasVariant") or []) if isinstance(v, dict)]
    variants: List[Dict[str, Any]] = []
    images: List[str] = list(_images(node.get("image")))
    prices: List = []
    any_in_stock = False
    colors_raw: List[str] = []

    for index, vnode in enumerate(variant_nodes):
        offers = _offer_list(vnode.get("offers"))
        pinfo = _price_and_currency(offers)
        v_sku = str(vnode.get("sku")).strip() if vnode.get("sku") else None
        v_barcode = _gtin(vnode)
        v_color = vnode.get("color")
        avail = pinfo["availability"]
        if avail == "in_stock":
            any_in_stock = True
        if pinfo["price"] is not None:
            prices.append(pinfo["price"])
        if v_color:
            colors_raw.append(v_color)
        for img in _images(vnode.get("image")):
            if img not in images:
                images.append(img)

        v = empty_variant()
        v.update({
            "variant_id": variant_id(pid, barcode=v_barcode, sku=v_sku,
                                     color=str(v_color) if v_color else None, index=index),
            "sku": v_sku,
            "barcode": v_barcode,
            "color": str(v_color).strip() if v_color else None,
            "price": pinfo["price"],
            "currency": normalize.normalize_currency(pinfo["currency"], currency),
            "available": (avail == "in_stock") if avail else None,
        })
        variants.append(v)

    resolved_currency = currency
    for vnode in variant_nodes:
        for offer in _offer_list(vnode.get("offers")):
            if offer.get("priceCurrency"):
                resolved_currency = normalize.normalize_currency(offer["priceCurrency"], currency)
                break
        if resolved_currency != currency:
            break

    record.update({
        "product_id": pid,
        "source": source,
        "vendor": brand,
        "brand": brand,
        "brand_normalized": brand.lower(),
        "title": title,
        "description": description,
        "category": normalize.normalize_category(node.get("category"), title),
        "subcategory": _text(node.get("category")),
        "gender": normalize.normalize_gender(node.get("category"), title),
        "price": min(prices) if prices else None,
        "original_price": None,
        "currency": resolved_currency,
        "availability": normalize.normalize_availability(any_in_stock) if variant_nodes else "",
        "rating": rating,
        "review_count": review_count,
        "image_urls": images,
        "main_image": images[0] if images else "",
        "product_url": product_url,
        "material": normalize.extract_materials(description, title),
        "colors": normalize.normalize_colors(colors_raw),
        "sizes": [],  # this ProductGroup varies by colour only; no size evidence
        "variants": variants,
        "attributes": {
            "platform": "jsonld",
            "schema_type": "ProductGroup",
            "product_group_id": group_id,
            "varies_by": node.get("variesBy"),
        },
        "scraped_at": _now_iso(),
    })
    return record


def map_jsonld_product(
    node: Dict[str, Any],
    product_url: str,
    source: str,
    currency: str = "EGP",
) -> Dict[str, Any]:
    """Convert a schema.org Product or ProductGroup node into a record.

    ProductGroup (with hasVariant) is expanded into a single record whose
    variants carry per colour sku, price and availability. A plain Product is
    mapped directly.
    """
    node_type = node.get("@type")
    types = node_type if isinstance(node_type, list) else [node_type]
    is_group = any(str(t).lower() == "productgroup" for t in types if t) or bool(node.get("hasVariant"))
    if is_group:
        return _map_product_group(node, product_url, source, currency)

    record = empty_product()

    title = _text(node.get("name"))
    description = _text(node.get("description"))
    brand = _brand(node.get("brand"))
    images = _images(node.get("image"))
    sku = (str(node.get("sku")).strip() if node.get("sku") else None)
    gtin = _gtin(node)
    mpn = (str(node.get("mpn")).strip() if node.get("mpn") else None)

    offers_list = _offer_list(node.get("offers"))
    price_info = _price_and_currency(offers_list)
    resolved_currency = normalize.normalize_currency(price_info["currency"], currency)

    colors = normalize.normalize_colors(
        node.get("color") if isinstance(node.get("color"), list) else [node.get("color")]
    )
    materials = normalize.extract_materials(
        " ".join(str(node.get(k, "")) for k in ("material",)), description, title
    )

    # Product-level size list (LC Waikiki, New Balance expose available sizes
    # as a schema.org "size" field rather than per-variant).
    raw_sizes = node.get("size")
    if isinstance(raw_sizes, list):
        sizes = [str(s).strip() for s in raw_sizes if s]
    elif raw_sizes:
        sizes = [str(raw_sizes).strip()]
    else:
        sizes = []

    # Gender: fall back to audience.suggestedGender (LC Waikiki pattern).
    gender = normalize.normalize_gender(node.get("category"), title)
    if not gender:
        audience = node.get("audience")
        if isinstance(audience, dict):
            suggested = str(audience.get("suggestedGender") or "").lower()
            if suggested in ("male", "men"):
                gender = "men"
            elif suggested in ("female", "women"):
                gender = "women"
            elif suggested == "unisex":
                gender = "unisex"

    # Adidas pattern: Product carries isVariantOf pointing to the ProductGroup.
    # Prefer productGroupID for the platform identifier so all colour variants
    # of the same style share a product_id and deduplication collapses them.
    is_variant_of = node.get("isVariantOf")
    group_id = None
    if isinstance(is_variant_of, dict):
        group_id = is_variant_of.get("productGroupID")

    rating = None
    review_count = None
    agg = node.get("aggregateRating")
    if isinstance(agg, dict):
        rating = normalize.to_decimal(agg.get("ratingValue"))
        rc = agg.get("reviewCount") or agg.get("ratingCount")
        review_count = int(rc) if str(rc).isdigit() else None

    pid = product_id(
        source,
        platform_product_id=group_id or node.get("productID") or node.get("sku"),
        product_url=product_url,
    )

    # Build variants from a list of offers when more than one is present.
    variants: List[Dict[str, Any]] = []
    if len(offers_list) > 1:
        for index, offer in enumerate(offers_list):
            v = empty_variant()
            v_sku = offer.get("sku")
            v.update(
                {
                    "variant_id": variant_id(pid, sku=v_sku, index=index),
                    "sku": v_sku,
                    "price": normalize.to_decimal(offer.get("price")),
                    "currency": normalize.normalize_currency(offer.get("priceCurrency"), resolved_currency),
                    "available": _availability(offer.get("availability")) == "in_stock"
                    if offer.get("availability") else None,
                }
            )
            variants.append(v)

    attrs: dict = {"platform": "jsonld", "mpn": mpn, "schema_type": node.get("@type")}
    if group_id:
        attrs["product_group_id"] = group_id

    record.update(
        {
            "product_id": pid,
            "source": source,
            "vendor": brand,
            "brand": brand,
            "brand_normalized": brand.lower(),
            "title": title,
            "description": description,
            "category": normalize.normalize_category(node.get("category"), title),
            "subcategory": _text(node.get("category")),
            "gender": gender,
            "price": price_info["price"],
            "original_price": None,
            "currency": resolved_currency,
            "availability": price_info["availability"],
            "sku": sku,
            "barcode": gtin,
            "gtin": gtin,
            "rating": rating,
            "review_count": review_count,
            "image_urls": images,
            "main_image": images[0] if images else "",
            "product_url": product_url,
            "material": materials,
            "colors": colors,
            "sizes": sizes,
            "variants": variants,
            "attributes": attrs,
            "scraped_at": _now_iso(),
        }
    )
    return record
