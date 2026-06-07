"""Generic Shopify spider.

Built directly on the working pattern preserved from the original prototype:
fetch the JSON the storefront already serves rather than parsing rendered
HTML. One spider serves every Shopify store; pick the store with a run time
argument.

Usage:
    scrapy crawl shopify -a store=townteam
    scrapy crawl shopify -a base_url=https://example.com -a slug=example
    scrapy crawl shopify -a store=townteam -a use_collections=true

By default it pages through the store wide ``/products.json`` endpoint, which
returns the entire catalog and avoids the brittle collection discovery step
that the prototype relied on. Set ``use_collections=true`` for the rare store
that disables the store wide endpoint but still serves per collection JSON.
"""

from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlparse

import scrapy
import tldextract

from ..core import shopify as shopify_mapper
from ..core.api import parse_json
from ..stores.shopify_stores import get_store

# Offline extractor (bundled public suffix snapshot, no network on use).
_TLD_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def _registrable_domain(url: str) -> str:
    """Return the registrable domain (eTLD+1) so apex, www and shop subdomains
    are all allowed, which prevents redirects between them from being filtered
    as offsite. Falls back to the bare host (for example an IP in tests)."""
    host = urlparse(url).netloc.split(":")[0]  # strip any port
    if not host:
        return ""
    ext = _TLD_EXTRACT(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}"
    return host


class ShopifySpider(scrapy.Spider):
    name = "shopify"

    PAGE_LIMIT = 250  # Shopify's maximum page size for products.json
    MAX_PAGES = 200   # safety cap so a misbehaving store cannot loop forever

    def __init__(
        self,
        store: Optional[str] = None,
        base_url: Optional[str] = None,
        slug: Optional[str] = None,
        currency: str = "EGP",
        use_collections: str = "false",
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if store:
            cfg = get_store(store)
            if cfg is None:
                raise ValueError(
                    f"unknown store slug '{store}'. See stores/shopify_stores.py"
                )
            self.base_url = cfg.base_url
            self.store_slug = cfg.slug
            self.currency = cfg.currency
            self.collections = list(cfg.collections)
        elif base_url:
            self.base_url = base_url.rstrip("/")
            self.store_slug = slug or urlparse(self.base_url).netloc.replace(".", "_")
            self.currency = currency
            self.collections = []
        else:
            raise ValueError("provide either -a store=<slug> or -a base_url=<url>")

        self.use_collections = str(use_collections).lower() == "true"
        self.allowed_domains = [_registrable_domain(self.base_url)]
        self.source = self.store_slug
        # Set once we switch from the store wide endpoint to collection
        # discovery, so the fallback can never trigger twice or loop.
        self._fellback = False

    def _stats_inc(self, key: str) -> None:
        crawler = getattr(self, "crawler", None)
        if crawler is not None and getattr(crawler, "stats", None) is not None:
            crawler.stats.inc_value(key)

    # -- request generation -------------------------------------------------
    # Scrapy 2.13 replaced the synchronous start_requests() seed method with an
    # async start() coroutine, and its default start() only reads start_urls.
    # To run on both old and new Scrapy we define both and delegate to a single
    # synchronous generator below.
    def _initial_requests(self) -> Iterable[scrapy.Request]:
        if self.use_collections and not self.collections:
            self._fellback = True  # explicit collection mode, no further fallback
            yield self._collections_index_request(page=1)
        elif self.collections:
            for path in self.collections:
                yield self._products_request(base=f"{self.base_url}{path}", mode="collection")
        else:
            yield self._products_request(base=self.base_url, mode="site")

    async def start(self):  # Scrapy >= 2.13
        for request in self._initial_requests():
            yield request

    def start_requests(self) -> Iterable[scrapy.Request]:  # Scrapy < 2.13
        return self._initial_requests()

    # -- request builders ---------------------------------------------------
    def _products_request(self, base: str, page: int = 1, mode: str = "site") -> scrapy.Request:
        url = f"{base.rstrip('/')}/products.json?limit={self.PAGE_LIMIT}&page={page}"
        return scrapy.Request(
            url=url,
            callback=self.parse_products,
            errback=self.on_error,
            meta={"base": base, "page": page, "mode": mode},
        )

    def _collections_index_request(self, page: int = 1) -> scrapy.Request:
        url = f"{self.base_url}/collections.json?limit=250&page={page}"
        return scrapy.Request(
            url=url,
            callback=self.parse_collections_index,
            errback=self.on_error,
            meta={"page": page, "mode": "collections-index"},
        )

    def _fallback_to_collections(self) -> Iterable[scrapy.Request]:
        """Switch from the store wide endpoint to per collection crawling.

        Triggered when /products.json is empty, non JSON (blocked), or errors.
        Many Shopify stores disable or do not populate the store wide endpoint
        but still serve /collections/<handle>/products.json, which is how the
        original prototype collected these stores.
        """
        if self._fellback:
            return
        self._fellback = True
        self.logger.info(
            "store wide products.json unusable for %s; falling back to collection discovery",
            self.source,
        )
        yield self._collections_index_request(page=1)

    # -- parsing ------------------------------------------------------------
    def parse_collections_index(self, response):
        data = parse_json(response)
        if not isinstance(data, dict):
            self.logger.warning(
                "collections.json not usable for %s (store may not be Shopify): %s",
                self.source, response.url,
            )
            return
        collections = data.get("collections", []) or []
        for collection in collections:
            handle = collection.get("handle")
            if handle:
                yield self._products_request(
                    base=f"{self.base_url}/collections/{handle}", mode="collection"
                )
        # Paginate the collection listing itself when it fills a page.
        page = response.meta.get("page", 1)
        if len(collections) == 250 and page < self.MAX_PAGES:
            yield self._collections_index_request(page=page + 1)

    def parse_products(self, response):
        mode = response.meta.get("mode", "site")
        page = response.meta.get("page", 1)
        base = response.meta.get("base", self.base_url)

        data = parse_json(response)
        if data is None:
            # Non JSON usually means an anti bot challenge or an HTML page.
            self.logger.warning("non JSON response at %s", response.url)
            if mode == "site":
                yield from self._fallback_to_collections()
            return

        products = data.get("products", []) if isinstance(data, dict) else []

        for product in products:
            try:
                record = shopify_mapper.map_shopify_product(
                    product, base_url=self.base_url, source=self.source, currency=self.currency,
                )
            except Exception as exc:  # one bad product never stops the crawl
                self.logger.error("failed to map product: %s", exc)
                self._stats_inc("egyscraper/map_errors")
                continue

            yield record

        # Paginate while a full page keeps coming back.
        if len(products) == self.PAGE_LIMIT and page < self.MAX_PAGES:
            yield self._products_request(base=base, page=page + 1, mode=mode)
        # An empty store wide first page means the endpoint is not populated;
        # try collection discovery instead.
        elif mode == "site" and page == 1 and len(products) == 0:
            yield from self._fallback_to_collections()

    def on_error(self, failure):
        request = failure.request
        self.logger.error("request failed: %s (%s)", request.url, failure.value)
        self._stats_inc("egyscraper/request_errors")
        # A failed store wide endpoint (404, 403, connection) also triggers the
        # collection fallback so a disabled or protected endpoint is recovered.
        if request.meta.get("mode") == "site":
            yield from self._fallback_to_collections()
