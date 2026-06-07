"""Registry of Shopify based stores.

Each entry is a store the generic Shopify spider can crawl with no custom
code: it only needs the origin url, a slug for output and ids, and the
currency. The ``confirmed`` flag marks stores verified against the original
prototype's working input list; the rest are strong candidates from the
target list that present as Shopify and should be verified before a full run
(visit ``<base_url>/products.json`` in a browser; a JSON product list means
it is Shopify).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ShopifyStore:
    slug: str
    base_url: str
    currency: str = "EGP"
    confirmed: bool = False
    # Optional explicit collection paths; empty means crawl the store wide
    # /products.json endpoint, which returns the full catalog on most stores.
    collections: List[str] = field(default_factory=list)


# Confirmed from the original Shopify prototype's base_urls.txt and validated by
# live crawls (each yields products through the store wide or collection path).
_CONFIRMED = [
    ShopifyStore("lablanca", "https://lablancaegypt.com", confirmed=True),
    ShopifyStore("townteam", "https://townteam.com", confirmed=True),
    ShopifyStore("iravin", "https://shop.iravin.com", confirmed=True),
    ShopifyStore("sigmafit", "https://sigmafiteg.com", confirmed=True),
    ShopifyStore("wayupsports", "https://wayupsports.com", confirmed=True),
    ShopifyStore("basiclook", "https://basiclook.com", confirmed=True),
    ShopifyStore("intersport", "https://www.intersport.com.eg", confirmed=True),
    ShopifyStore("gorillaoutfit", "https://gorillaoutfit.com", confirmed=True),
]
# Note: mitcha was previously listed here but live crawls return HTML (status
# 200) from both /products.json and /collections.json, so it is not a Shopify
# storefront. It is handled as a custom store (see stores/classification.py).

# Candidates from the target list that appear to run on Shopify. Verify each
# before relying on it in production.
_CANDIDATES = [
    ShopifyStore("carinawear", "https://carinawear.com"),
    ShopifyStore("tomatostore", "https://tomatostore.com"),
    ShopifyStore("magmasportswear", "https://magmasportswear.com"),
    ShopifyStore("pinkshop", "https://pinkshopeg.com"),
    ShopifyStore("tiehouse", "https://tie-house.com"),
    ShopifyStore("youremma", "https://youremma.com"),
    ShopifyStore("izzyapparel", "https://izzyapparel.com"),
    ShopifyStore("mobaco", "https://mobaco.com"),
    ShopifyStore("lavitoscarf", "https://lavitoscarf.com"),
    ShopifyStore("andora", "https://andoraeg.com"),
    # Lower confidence, verify with /products.json before trusting:
    ShopifyStore("americaneagle", "https://americaneagle.com.eg"),
    ShopifyStore("accessorize", "https://accessorize.com"),
    # Locale prefixed Shopify Plus store; the path returns the Egypt catalog.
    ShopifyStore("aloyoga", "https://www.aloyoga.com/en-eg"),
]

SHOPIFY_STORES: Dict[str, ShopifyStore] = {
    store.slug: store for store in (_CONFIRMED + _CANDIDATES)
}


def get_store(slug: str) -> Optional[ShopifyStore]:
    return SHOPIFY_STORES.get(slug)


def confirmed_slugs() -> List[str]:
    return [s.slug for s in SHOPIFY_STORES.values() if s.confirmed]


def all_slugs() -> List[str]:
    return list(SHOPIFY_STORES.keys())
