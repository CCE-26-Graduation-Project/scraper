"""Deterministic product and variant identifiers.

The same physical listing must receive the same id on every crawl so that re
crawling updates a row rather than creating a duplicate. Ids are content free
SHA256 hashes of stable inputs, never random.

Identity is scoped at two granularities:

  product_id  identifies a product listing at one merchant. It uses the
              strongest stable PRODUCT level identifier:
                  platform product id  >  product handle  >  canonical url
              Variant level codes (sku, barcode) are intentionally NOT used
              here, because a product has many variants with different codes.

  variant_id  identifies one variant within a product. It uses the strongest
              stable VARIANT level identifier:
                  barcode  >  gtin  >  sku  >  platform variant id  >
                  size and colour  >  positional index
              Barcode and gtin lead because they are the cross store match key.
"""

from __future__ import annotations

import hashlib
from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean(value: Optional[object]) -> str:
    return str(value).strip() if value is not None else ""


def canonical_url(url: str) -> str:
    """Strip query string and fragment so url based ids stay stable."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def product_id(
    merchant: str,
    platform_product_id: Optional[object] = None,
    handle: Optional[str] = None,
    product_url: Optional[str] = None,
) -> str:
    """Return a stable SHA256 id for a product listing at one merchant.

    Fallback hierarchy: platform product id, then handle, then canonical url.
    Raises if none of these are usable, because an item with no stable identity
    should never be assigned a random or empty id.
    """
    merchant = (merchant or "").strip().lower()
    if not merchant:
        raise ValueError("merchant is required to build a deterministic product id")

    pid = _clean(platform_product_id)
    if pid:
        return _sha256(f"{merchant}:pid:{pid}")

    h = _clean(handle)
    if h:
        return _sha256(f"{merchant}:handle:{h.lower()}")

    url = canonical_url(product_url or "")
    if url:
        return _sha256(f"{merchant}:url:{url}")

    raise ValueError(
        "product id needs a platform product id, a handle, or a product url"
    )


def variant_id(
    product_id_value: str,
    barcode: Optional[str] = None,
    gtin: Optional[str] = None,
    sku: Optional[str] = None,
    platform_variant_id: Optional[object] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    index: Optional[int] = None,
) -> str:
    """Return a stable SHA256 id for one variant within a product.

    Always resolvable: when no real identifier is present it falls back to size
    and colour, and finally to a positional index, so every variant gets a
    deterministic id.
    """
    if not product_id_value:
        raise ValueError("a product_id is required to build a variant id")

    for label, value in (
        ("barcode", barcode),
        ("gtin", gtin),
        ("sku", sku),
        ("pvid", platform_variant_id),
    ):
        cleaned = _clean(value)
        if cleaned:
            return _sha256(f"{product_id_value}:{label}:{cleaned}")

    size_color = f"{_clean(size)}|{_clean(color)}".strip("|")
    if size_color:
        return _sha256(f"{product_id_value}:sc:{size_color.lower()}")

    return _sha256(f"{product_id_value}:idx:{index if index is not None else 0}")
