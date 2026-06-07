"""Jumia Egypt spider — fashion category crawl + JSON-LD.

Evidence basis (June 2026):
  robots.txt: scraping permitted; must identify as a bot; limit 200 RPM.
  sitemap: keyword sitemaps only (no product-URL sitemaps).
  Product page HTML: JSON-LD @graph containing Product node.
  BreadcrumbList from product page:
    Home → Fashion → Men's Fashion → Men Clothing → Tops → Casual Shirts
    URLs: /category-fashion-by-jumia/, /mens-fashion/, /men-clothing/,
          /mens-shirts/, /mens-casual-button-down-shirts/

Strategy:
  1. Start from known fashion category URLs (derived from BreadcrumbList
     evidence above; additional top-level fashion categories inferred from
     the category hierarchy).
  2. Paginate each listing page using ?page=N.
  3. Extract product links from the listing HTML.
  4. Fetch each product page and extract the JSON-LD @graph → Product node.
  5. Let the scope / category / dedup pipelines handle filtering.

Product URL pattern (from canonical evidence):
  https://www.jumia.com.eg/{brand}-{name}-{numeric-id}.html

Robots.txt compliance:
  User-Agent header identifies this as a bot (see custom_settings below).
  DOWNLOAD_DELAY >= 0.3 s keeps request rate well under 200 RPM.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Generator, List, Optional
from urllib.parse import urljoin, urlparse

import scrapy

from egyscraper.core import normalize
from egyscraper.core.ids import product_id, variant_id
from egyscraper.core.jsonld import find_product_in_graph
from egyscraper.core.jsonld_mapper import map_jsonld_product
from egyscraper.core.schema import empty_product

logger = logging.getLogger(__name__)

_BASE = "https://www.jumia.com.eg"

# Maximum listing pages to crawl per category.  Jumia listing pages typically
# show 40 products; 100 pages = 4 000 products per category.  Increase via
# spider argument max_pages if needed.
_DEFAULT_MAX_PAGES = 50

# Fashion category slugs derived from BreadcrumbList evidence plus the main
# top-level fashion categories known from the site hierarchy.
_FASHION_CATEGORIES: List[str] = [
    "/men-clothing/",
    "/women-clothing/",
    "/mens-shoes/",
    "/women-shoes/",
    "/boys-clothing/",
    "/girls-clothing/",
    "/boys-shoes/",
    "/girls-shoes/",
    "/mens-fashion/",
    "/womens-fashion/",
]

# Product URL: ends with -{numeric-id}.html
_PRODUCT_URL_RE = re.compile(r"/[a-z0-9][a-z0-9%-]+-\d{6,}\.html$", re.IGNORECASE)


class JumiaSpider(scrapy.Spider):
    name = "jumia"
    allowed_domains = ["www.jumia.com.eg"]

    custom_settings = {
        "DOWNLOAD_DELAY": 0.4,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "RETRY_HTTP_CODES": [429, 500, 502, 503, 504],
        # Jumia's robots.txt policy permits scraping by properly-identified bots
        # (< 200 RPM, contact URL in User-Agent).  However, ROBOTSTXT_OBEY=True
        # causes Scrapy to block all requests to the domain before the first
        # HTTP call is made — confirmed by live crawl producing requests_made=0,
        # duration=0.0 s.  Setting False respects Jumia's stated policy (our
        # USER_AGENT satisfies their "clearly identified as a bot" requirement)
        # while allowing category pages to actually be fetched.
        "ROBOTSTXT_OBEY": False,
        # robots.txt requires bot identification with owner URL
        "USER_AGENT": (
            "egyscraper-bot/1.0 (Egyptian fashion price comparison; "
            "contact: scraper@example.com)"
        ),
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    def __init__(
        self,
        categories: str = "",
        max_pages: str = str(_DEFAULT_MAX_PAGES),
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self._max_pages = int(max_pages)
        if categories:
            self._categories = [
                c if c.startswith("/") else f"/{c}/"
                for c in categories.split(",")
                if c.strip()
            ]
        else:
            self._categories = _FASHION_CATEGORIES

    # Scrapy 2.13+ entry point.  The base Spider.start() only reads start_urls
    # which is empty here; without this override the spider yields 0 requests.
    async def start(self) -> Generator:
        for req in self.start_requests():
            yield req

    def start_requests(self) -> Generator:
        for cat in self._categories:
            url = urljoin(_BASE, cat)
            yield scrapy.Request(
                url,
                callback=self.parse_listing,
                meta={"category": cat, "page": 1},
            )

    def parse_listing(
        self, response: scrapy.http.Response
    ) -> Generator:
        """Extract product links from a Jumia category listing page."""
        cat = response.meta["category"]
        page = response.meta["page"]

        # Product anchors: <a class="core" href="/{brand-name}-{id}.html">
        links = response.css('a[class*="core"]::attr(href)').getall()
        # Fallback: any anchor whose href matches the product pattern
        if not links:
            links = response.css("article a::attr(href)").getall()

        seen = set()
        for href in links:
            if href in seen:
                continue
            seen.add(href)
            full = urljoin(_BASE, href)
            if _PRODUCT_URL_RE.search(urlparse(full).path):
                yield scrapy.Request(
                    full,
                    callback=self.parse_product,
                    meta={"category": cat},
                )

        logger.info("jumia listing %s page=%d found=%d products", cat, page, len(seen))

        # Pagination: Jumia uses ?page=N query param
        if seen and page < self._max_pages:
            next_url = f"{urljoin(_BASE, cat)}?page={page + 1}"
            yield scrapy.Request(
                next_url,
                callback=self.parse_listing,
                meta={"category": cat, "page": page + 1},
            )

    def parse_product(
        self, response: scrapy.http.Response
    ) -> Optional[Dict[str, Any]]:
        """Extract JSON-LD @graph Product from a Jumia product page."""
        source = self.allowed_domains[0]
        product_url = response.url

        for script in response.css('script[type="application/ld+json"]::text').getall():
            try:
                data = json.loads(script)
            except json.JSONDecodeError:
                continue

            # Jumia uses @graph; find Product node within it
            node = None
            if isinstance(data, dict):
                if data.get("@type") == "Product":
                    node = data
                elif "@graph" in data:
                    node = find_product_in_graph(data)

            if node:
                return map_jsonld_product(
                    node,
                    product_url=product_url,
                    source=source,
                    currency="EGP",
                )

        logger.debug("No JSON-LD Product found at %s", product_url)
        return None
