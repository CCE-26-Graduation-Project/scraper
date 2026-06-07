"""Registry of custom stores served by the generic JSON LD spider.

Each entry is a non Shopify store whose product pages embed schema.org Product
data. The spider needs only a base url, a product url pattern, and optionally a
sitemap url; the extraction is generic.

Evidence status (June 2026):
  decathlon   confirmed from real product page
  lcwaikiki   confirmed from real product page
  lacoste     confirmed from real product page
  adidas      confirmed from real product page + sitemap (5 144 URLs)
  newbalance  confirmed JSON-LD present; images missing from saved HTML
  jumia       handled by jumia spider (category crawl), not this registry
  noon        handled by noon spider (catalog API), not this registry
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class JsonLdStore:
    slug: str
    base_url: str
    product_pattern: str           # regex matching product page urls
    sitemap: Optional[str] = None  # defaults to robots.txt discovery
    currency: str = "EGP"
    note: str = ""
    # When False, ValidationPipeline skips the image_urls check for this
    # store.  Set for stores whose product pages render images via JS so
    # JSON-LD always has image:[] (New Balance is the known case).
    require_images: bool = True
    # Per-request headers sent with every sitemap and product page request for
    # this store.  Used to pass browser-like Accept / Referer headers that
    # reduce bot detection on SFCC and Adidas CDN endpoints.
    extra_headers: dict = None


_STORES = [
    # ── Verified from real evidence ─────────────────────────────────────────
    JsonLdStore(
        "decathlon",
        "https://www.decathlon.eg",
        r"/en/p/",
        sitemap="https://www.decathlon.eg/sitemap-en-index.xml",
        note="ProductGroup JSON-LD; verified June 2026.",
    ),
    JsonLdStore(
        "lcwaikiki",
        "https://www.lcwaikiki.eg",
        # Product URLs: /en/{slug}-o-{numeric-id}
        r"/en/.*-o-\d+",
        sitemap="https://www.lcwaikiki.eg/sitemap/api/FeedXml/EG/product_sitemap_EN.xml",
        note="Rich JSON-LD Product with color[], size[], gtin13, audience.suggestedGender. "
             "Verified from real product page June 2026.",
    ),
    JsonLdStore(
        "lacoste",
        "https://www.lacoste.com.eg",
        # Product URLs: /en/{category}/{slug}/{SKU}.html  e.g. CH5699-00.html
        r"/en/[^/]+/[^/]+/[A-Z][A-Z0-9]+-\d+\.html",
        # sitemap_index.xml → sitemap_0-category, sitemap_1-content, sitemap_2 (products).
        # Live crawl: 7 requests, 0 retries, 2 failures (HTTP 404 — NOT in RETRY_HTTP_CODES
        # so retries=0 is proof of 404, not 403/500).  Two scenarios consistent with
        # evidence: (A) sitemap_2.xml URL changed after evidence collection, OR
        # (B) SFCC WAF returns fake-404 to non-browser requests.
        # Fix: add Referer and browser Accept headers to reduce WAF detection.
        sitemap="https://www.lacoste.com.eg/sitemap_index.xml",
        extra_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.lacoste.com.eg/en/lacoste/men",
            "Cache-Control": "no-cache",
        },
        note="SFCC (Demandware/Chalhoub). Single-image JSON-LD; no sizes. "
             "Browser headers added for WAF bypass. Verified product page June 2026.",
    ),
    JsonLdStore(
        "adidas",
        "https://www.adidas.com.eg",
        # Product URLs: /en/{slug}/{SKU}.html  SKU is 6 uppercase alphanumeric chars
        r"/en/[^/]+/[A-Z0-9]{6}\.html",
        # robots.txt declares both /en/sitemap-index and /en/sitemap.
        # Live crawl: requests_made=32, retries=24, failures=7, scope_seen=0.
        # Arithmetic: 7 unique sitemap URLs tried × ~4 attempts = ~31 requests
        # + 1 robots.txt success = 32.  All sitemaps returned retry-eligible
        # HTTP codes (403/500) → CDN bot detection.
        # Fix: add browser-like headers to reduce detection rate.
        sitemap="https://www.adidas.com.eg/en/sitemap",
        extra_headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.adidas.com.eg/en/men-clothing",
            "Cache-Control": "no-cache",
        },
        note="Custom Adidas platform. JSON-LD Product with isVariantOf.ProductGroup. "
             "HAR shows reCAPTCHA on product pages. Browser headers added to reduce "
             "CDN-level bot detection on sitemaps. May still need proxy for product pages.",
    ),
    JsonLdStore(
        "newbalance",
        "https://www.newbalance.com.eg",
        # Product URLs: /en/buy-{slug}
        r"/en/buy-[a-z0-9-]+$",
        # robots declares /sitemap.xml
        # require_images=False because New Balance renders images via JS;
        # JSON-LD always has image:[] in the server-rendered HTML.
        # Products are exported without images and Playwright can backfill later.
        require_images=False,
        note="Custom platform. JSON-LD has name, sku, brand, offers but image:[] is "
             "empty in the saved HTML (JS-rendered images). Exported without images; "
             "Playwright required to recover image URLs.",
    ),
    # ── Blocked / needs proxy ────────────────────────────────────────────────
    JsonLdStore(
        "defacto",
        "https://defacto.com.eg",
        r"/p/|/product/",
        note="403 on first attempt; needs proxy or Playwright.",
    ),
]

JSONLD_STORES: Dict[str, JsonLdStore] = {s.slug: s for s in _STORES}


def get_store(slug: str) -> Optional[JsonLdStore]:
    return JSONLD_STORES.get(slug)


def all_slugs() -> List[str]:
    return list(JSONLD_STORES.keys())
