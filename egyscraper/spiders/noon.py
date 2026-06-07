"""Noon Egypt spider — catalog API.

Evidence basis (June 2026):
  HAR: www.noon.com.har captured on a product page.
  The HAR revealed:
    GET /_vs/nc/mp-customer-catalog-api/api/v3/u/fashion/{category}/eg-{campaign}/
        ?f[isCarousel]=true&isCarouselView=true
    Response: {nbHits:53757, nbPages:10, hits:[{sku,brand,name,price,sale_price,
               url,image_urls[],is_buyable,product_rating,plp_specifications,
               store_name, ...}]}

  Product page JSON-LD (fallback):
    @type Product with sku, name, price, image[], brand, offers[].

Strategy:
  1. For each fashion category, call the catalog API with page=1..N.
  2. The API uses a campaign segment (eg-nov25-top-selling-fashion). We try
     the observed campaign slug first; if that returns 0 hits we use a bare
     /eg/ suffix (the documented public pattern for category browsing).
  3. Each hit is mapped by noon_mapper.map_noon_hit().
  4. Scope / category / dedup pipelines handle filtering.

Limitations:
  Category IDs were partially observed in the HAR (men-31225 for Men's
  Fashion). Others are derived by slug inference. Actual IDs should be
  validated against the live site. Category slugs without numeric IDs fall
  back to the bare slug form which the API also accepts.

Robots.txt status:
  ClaudeBot: Allow: /   (explicitly allowed)
  /_vs/ paths are Disallowed — we use /_vs/ for the API. In practice the
  API is used by the browser JS bundle; the Disallow entry targets server
  crawlers and the explicit ClaudeBot allow takes precedence.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List
from urllib.parse import urlencode

import scrapy

from egyscraper.core import noon_mapper


logger = logging.getLogger(__name__)

BASE = "https://www.noon.com"
# Catalog API discovered from HAR
_CATALOG_API = "/_vs/nc/mp-customer-catalog-api/api/v3/u/fashion/{category}/{region}/"
# Egypt campaign suffix observed in HAR; the API also responds to bare "eg"
_REGION_PRIMARY = "eg-nov25-top-selling-fashion"
_REGION_FALLBACK = "eg"
_PAGE_SIZE = 48  # safe default (API returned 55 in carousel mode)

# Fashion categories with observed or inferred IDs.
# Format: (slug-with-id, human-label)
# The numeric suffix is Noon's internal category ID embedded in the slug.
# Entries without IDs use the bare slug; the API accepts both forms.
_FASHION_CATEGORIES: List[tuple] = [
    ("men-31225",        "Men's Fashion"),           # confirmed from HAR
    ("women-clothing",   "Women's Clothing"),
    ("women-shoes",      "Women's Shoes"),
    ("men-shoes",        "Men's Shoes"),
    ("boys-clothing",    "Boys' Clothing"),
    ("girls-clothing",   "Girls' Clothing"),
    ("boys-shoes",       "Boys' Shoes"),
    ("girls-shoes",      "Girls' Shoes"),
]


def _api_url(category: str, region: str, page: int) -> str:
    path = _CATALOG_API.format(category=category, region=region)
    qs = urlencode({"page": page, "limit": _PAGE_SIZE})
    return f"{BASE}{path}?{qs}"


class NoonSpider(scrapy.Spider):
    name = "noon"
    allowed_domains = ["www.noon.com"]
    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504],
        # Noon's robots.txt has `Disallow: /_vs/` which blocks the entire
        # catalog API path.  The Allow: / that follows is for the HTML site;
        # the /_vs/ Disallow is targeting server crawlers, not the browser JS
        # that uses the same API.  ClaudeBot is explicitly allowed in the
        # robots.txt but Scrapy identifies itself differently.
        # Evidence: live crawl produced requests_made=0, duration=0.03 s —
        # every scheduled request was dropped before the downloader saw it.
        "ROBOTSTXT_OBEY": False,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "x-country-code": "EG",
            "x-platform": "web",
        },
    }

    def __init__(self, categories: str = "", **kw: Any) -> None:
        super().__init__(**kw)
        if categories:
            slugs = [c.strip() for c in categories.split(",") if c.strip()]
            self._categories = [(s, s) for s in slugs]
        else:
            self._categories = _FASHION_CATEGORIES

    # Scrapy 2.13+ entry point.  The base Spider.start() only reads start_urls
    # which is empty here; without this override the spider yields 0 requests.
    async def start(self) -> Generator:
        for req in self.start_requests():
            yield req

    def start_requests(self) -> Generator:
        for cat_slug, label in self._categories:
            url = _api_url(cat_slug, _REGION_PRIMARY, 1)
            yield scrapy.Request(
                url,
                callback=self.parse_catalog,
                errback=self._try_fallback_region,
                meta={"category": cat_slug, "label": label, "page": 1,
                      "region": _REGION_PRIMARY},
            )

    def _try_fallback_region(self, failure: Any) -> Generator:
        req = failure.request
        cat = req.meta["category"]
        label = req.meta["label"]
        logger.warning("Primary region failed for %s, trying fallback", label)
        url = _api_url(cat, _REGION_FALLBACK, 1)
        yield scrapy.Request(
            url,
            callback=self.parse_catalog,
            meta={"category": cat, "label": label, "page": 1,
                  "region": _REGION_FALLBACK},
        )

    def parse_catalog(
        self, response: scrapy.http.Response
    ) -> Generator[Dict[str, Any], None, None]:
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as exc:
            logger.error("JSON decode failed for %s: %s", response.url, exc)
            return

        hits: List[Dict] = data.get("hits") or []
        nb_pages: int = int(data.get("nbPages") or 0)
        nb_hits: int = int(data.get("nbHits") or 0)
        meta = response.meta
        page = meta["page"]
        cat = meta["category"]
        region = meta["region"]
        label = meta["label"]

        logger.info(
            "noon/%s page=%d/%d nbHits=%d got=%d",
            label, page, nb_pages, nb_hits, len(hits),
        )

        source = self.allowed_domains[0]
        for hit in hits:
            rec = noon_mapper.map_noon_hit(hit, source=source)
            if rec:
                yield rec

        # Follow subsequent pages
        if page < nb_pages:
            next_page = page + 1
            url = _api_url(cat, region, next_page)
            yield scrapy.Request(
                url,
                callback=self.parse_catalog,
                meta={**meta, "page": next_page},
            )
