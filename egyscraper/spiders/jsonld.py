"""Generic JSON LD spider for structured custom (non Shopify) stores.

Many custom storefronts expose a sitemap and embed a schema.org Product block
on each product page. This one spider serves all of them: point it at a store,
give it a pattern that matches product urls, and it walks the sitemap, fetches
each product page, extracts the Product JSON LD, and maps it to the standard
schema. No per store parsing code is needed, only a little configuration.

Usage:
    scrapy crawl jsonld -a base_url=https://defacto.com.eg -a slug=defacto \
        -a product_pattern="/p/"
    scrapy crawl jsonld -a base_url=https://example.com -a slug=example \
        -a sitemap=https://example.com/sitemap_products.xml -a product_pattern="/product/"

Each target store needs its sitemap url (defaults to /sitemap.xml) and a regex
that identifies product urls, both verified once against the live site. The
extraction itself is generic and tested.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional
from urllib.parse import urlparse

import scrapy

from ..core import jsonld
from ..core.jsonld_mapper import map_jsonld_product

_LOC = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)


def _registrable_domain(url: str) -> str:
    import tldextract
    host = urlparse(url).netloc.split(":")[0]
    ext = tldextract.TLDExtract(suffix_list_urls=())(host)
    return f"{ext.domain}.{ext.suffix}" if ext.domain and ext.suffix else host


class JsonLdSpider(scrapy.Spider):
    name = "jsonld"

    MAX_SITEMAPS = 200      # safety cap on nested sitemap fan out
    MAX_PRODUCTS = 100000   # safety cap on product pages per crawl

    def __init__(
        self,
        store: Optional[str] = None,
        base_url: Optional[str] = None,
        slug: Optional[str] = None,
        sitemap: Optional[str] = None,
        product_pattern: str = r"/product",
        currency: str = "EGP",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if store:
            from ..stores.jsonld_stores import get_store
            cfg = get_store(store)
            if cfg is None:
                raise ValueError(f"unknown jsonld store '{store}'. See stores/jsonld_stores.py")
            base_url = cfg.base_url
            slug = cfg.slug
            sitemap = cfg.sitemap
            product_pattern = cfg.product_pattern
            currency = cfg.currency
            self.images_required = cfg.require_images
            self.extra_headers = cfg.extra_headers or {}
        else:
            self.images_required = True
            self.extra_headers = {}
        if not base_url:
            raise ValueError(
                "provide -a store=<slug> or -a base_url=<url> (with -a product_pattern=<regex>)"
            )

        self.base_url = base_url.rstrip("/")
        self.store_slug = slug or urlparse(self.base_url).netloc.replace(".", "_")
        self.source = self.store_slug
        self.currency = currency
        self.sitemap_url = sitemap or f"{self.base_url}/sitemap.xml"
        self.product_re = re.compile(product_pattern)
        self.allowed_domains = [_registrable_domain(self.base_url)]
        self._sitemaps_seen = 0
        self._products_seen = 0
        self._sitemaps_requested = set()
        self._tried_candidates = False

    def _initial_requests(self) -> Iterable[scrapy.Request]:
        # Ask robots.txt for its declared sitemaps, and try the configured one
        # in parallel. Whichever yields product urls first wins; duplicates are
        # de duplicated by url.
        yield scrapy.Request(
            f"{self.base_url}/robots.txt", callback=self.parse_robots,
            errback=self.on_error, meta={"kind": "robots"},
        )
        yield self._sitemap_request(self.sitemap_url)

    def _sitemap_request(self, url: str) -> Optional[scrapy.Request]:
        if url in self._sitemaps_requested:
            return None
        self._sitemaps_requested.add(url)
        return scrapy.Request(url, callback=self.parse_sitemap, errback=self.on_error,
                              meta={"kind": "sitemap"},
                              headers=self.extra_headers or {})

    def _candidate_sitemaps(self) -> Iterable[scrapy.Request]:
        """Common sitemap locations, tried when the primary one fails."""
        for path in ("/sitemap_index.xml", "/sitemap-index.xml", "/sitemap1.xml",
                     "/sitemap/sitemap.xml", "/sitemaps.xml"):
            req = self._sitemap_request(f"{self.base_url}{path}")
            if req is not None:
                yield req

    async def start(self):  # Scrapy >= 2.13
        for request in self._initial_requests():
            yield request

    def start_requests(self) -> Iterable[scrapy.Request]:  # Scrapy < 2.13
        return self._initial_requests()

    def parse_robots(self, response):
        """Extract Sitemap: directives from robots.txt and crawl each."""
        found = False
        for line in response.text.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                url = line.split(":", 1)[1].strip()
                req = self._sitemap_request(url)
                if req is not None:
                    found = True
                    yield req
        if not found:
            self.logger.debug("no Sitemap directives in robots.txt for %s", self.source)

    def parse_sitemap(self, response):
        """Walk a sitemap or sitemap index, following nested sitemaps and
        dispatching product urls to parse_product."""
        locs = [m.strip() for m in _LOC.findall(response.text) if m.strip()]
        for loc in locs:
            if loc.endswith(".xml") or "sitemap" in loc.lower():
                if self._sitemaps_seen < self.MAX_SITEMAPS:
                    req = self._sitemap_request(loc)
                    if req is not None:
                        self._sitemaps_seen += 1
                        yield req
            elif self.product_re.search(loc) and self._products_seen < self.MAX_PRODUCTS:
                self._products_seen += 1
                yield scrapy.Request(loc, callback=self.parse_product, errback=self.on_error,
                                     headers=self.extra_headers or {})

    def parse_product(self, response):
        node = jsonld.find_product_or_group(response.text)
        if not node:
            self.logger.debug("no Product JSON LD at %s", response.url)
            self._stats_inc("egyscraper/no_jsonld")
            return
        try:
            record = map_jsonld_product(node, response.url, self.source, self.currency)
        except Exception as exc:  # one bad page never stops the crawl
            self.logger.error("failed to map %s: %s", response.url, exc)
            self._stats_inc("egyscraper/map_errors")
            return
        yield record

    def on_error(self, failure):
        request = failure.request
        self.logger.error("request failed: %s (%s)", request.url, failure.value)
        self._stats_inc("egyscraper/request_errors")
        # If a sitemap fetch failed and we have not yet tried the common
        # alternate locations, try them now (once). A blocked store (403) will
        # also fail these, which is the signal that it needs a proxy or
        # Playwright rather than another url.
        if request.meta.get("kind") in ("sitemap", "robots") and not self._tried_candidates:
            self._tried_candidates = True
            self.logger.info("primary sitemap unavailable for %s; trying common locations", self.source)
            yield from self._candidate_sitemaps()

    def _stats_inc(self, key: str) -> None:
        crawler = getattr(self, "crawler", None)
        if crawler is not None and getattr(crawler, "stats", None) is not None:
            crawler.stats.inc_value(key)
