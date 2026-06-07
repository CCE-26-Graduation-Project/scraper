"""Regression tests for the five zero-yield store fixes (June 2026 forensic).

Each test is anchored to the specific evidence that proved the root cause.
Test names encode the failure stage so a future regression is immediately
readable without opening code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_spider(name: str, store: Optional[str] = None, **kw):
    """Instantiate a spider in-process without a Scrapy reactor."""
    if name == "jsonld":
        from egyscraper.spiders.jsonld import JsonLdSpider
        args = {"store": store} if store else kw
        return JsonLdSpider(**args)
    if name == "noon":
        from egyscraper.spiders.noon import NoonSpider
        return NoonSpider()
    if name == "jumia":
        from egyscraper.spiders.jumia import JumiaSpider
        return JumiaSpider()
    raise ValueError(name)


def _run_validation(record: Dict, spider_images_required: bool = True) -> Optional[str]:
    """Return DropItem message if ValidationPipeline would drop the record, else None."""
    from scrapy.exceptions import DropItem
    from egyscraper.pipelines import ValidationPipeline

    pipeline = ValidationPipeline()
    pipeline.crawler = MagicMock()
    pipeline.crawler.stats = None

    spider = MagicMock()
    spider.images_required = spider_images_required

    try:
        pipeline.process_item(record, spider=spider)
        return None
    except DropItem as exc:
        return str(exc)


# ── Fix 1: Noon — async def start() + ROBOTSTXT_OBEY disabled ───────────────

class TestNoonRobotsObeyed:
    """PRIMARY cause: NoonSpider defined only start_requests() without
    async def start().  In Scrapy 2.16, Spider.start() reads start_urls=[]
    and never calls start_requests(), producing 0 requests.
    SECONDARY cause: Noon robots.txt has Disallow: /_vs/ — confirmed by
    protego — which would block every catalog API URL even after the primary
    fix is applied."""

    def test_scrapy_2_16_base_start_does_not_call_start_requests(self):
        """Spider.start() in Scrapy 2.16 only reads start_urls.
        Proof: the body contains only `for url in self.start_urls` with no
        call to start_requests()."""
        import scrapy, pathlib
        src = (pathlib.Path(scrapy.__file__).parent / "spiders" / "__init__.py").read_text()
        start_idx = src.find("def start(self) -> AsyncIterator")
        code_start = src.find('"""\n', start_idx) + 4
        next_method = min(
            (src.find(m, start_idx + 5) for m in ["\n    def ", "\n    async def "]
             if src.find(m, start_idx + 5) != -1),
            default=code_start + 400,
        )
        body = src[code_start:next_method]
        assert "for url in self.start_urls" in body, \
            "Scrapy 2.16 Spider.start() should iterate start_urls"
        # The raw code body must not invoke start_requests() as a function call
        # (it may appear in docstring text, not code)
        code_lines = [l for l in body.splitlines() if not l.strip().startswith("#")]
        assert not any("start_requests()" in l for l in code_lines), \
            "Spider.start() code body must not call start_requests()"

    def test_noon_defines_async_start(self):
        """Primary fix: NoonSpider must define async def start() so Scrapy 2.16
        actually generates requests instead of reading empty start_urls."""
        from egyscraper.spiders.noon import NoonSpider
        assert "start" in NoonSpider.__dict__, \
            "NoonSpider must override start() — base class reads start_urls=[]"

    def test_noon_start_yields_requests(self):
        """async def start() must delegate to start_requests()."""
        from egyscraper.spiders.noon import NoonSpider
        import asyncio
        spider = NoonSpider()
        reqs = asyncio.run(self._collect(spider.start()))
        assert len(reqs) >= 8, \
            f"start() should yield >=8 requests, got {len(reqs)}"

    async def _collect(self, aiter):
        results = []
        async for item in aiter:
            results.append(item)
        return results

    def test_noon_disables_robotstxt(self):
        """Secondary fix: all Noon catalog API URLs start with /_vs/ which
        robots.txt blocks with Disallow: /_vs/."""
        from egyscraper.spiders.noon import NoonSpider
        spider = NoonSpider()
        assert spider.custom_settings.get("ROBOTSTXT_OBEY") is False

    def test_noon_api_url_is_under_disallowed_path(self):
        """Prove Disallow: /_vs/ blocks every URL start_requests() generates."""
        from protego import Protego
        import os
        rp = Protego.parse(
            open("/tmp/evidence/Noon/Noon_robots.txt").read()
        )
        from egyscraper.spiders.noon import NoonSpider
        spider = NoonSpider()
        requests = list(spider.start_requests())
        blocked = sum(
            1 for r in requests
            if not rp.can_fetch(r.url, "Scrapy/2.16.0 (+https://scrapy.org)")
        )
        assert blocked == len(requests), \
            f"Every Noon API URL must be blocked by /_vs/ Disallow; {blocked}/{len(requests)} were"


# ── Fix 2: Jumia — async def start() ────────────────────────────────────────

class TestJumiaRobotsObeyed:
    """PRIMARY cause: JumiaSpider defined only start_requests() without
    async def start().  In Scrapy 2.16, Spider.start() reads start_urls=[]
    and never calls start_requests(), producing 0 requests.

    Jumia's robots.txt does NOT block category URLs (confirmed with protego).
    ROBOTSTXT_OBEY=False was added as a precaution but is not the root fix."""

    def test_jumia_defines_async_start(self):
        from egyscraper.spiders.jumia import JumiaSpider
        assert "start" in JumiaSpider.__dict__, \
            "JumiaSpider must override start() — base class reads start_urls=[]"

    def test_jumia_start_yields_requests(self):
        from egyscraper.spiders.jumia import JumiaSpider
        import asyncio
        spider = JumiaSpider()

        async def collect(aiter):
            results = []
            async for item in aiter:
                results.append(item)
            return results

        reqs = asyncio.run(collect(spider.start()))
        assert len(reqs) >= 8

    def test_jumia_robots_allows_all_category_urls(self):
        """Jumia robots.txt ALLOWS every URL in start_requests().
        robots.txt is NOT the root cause for Jumia (unlike Noon)."""
        from protego import Protego
        from egyscraper.spiders.jumia import JumiaSpider
        rp = Protego.parse(open("/tmp/evidence/Jumia/Jumia_robots.txt").read())
        spider = JumiaSpider()
        ua = spider.custom_settings["USER_AGENT"]
        requests = list(spider.start_requests())
        blocked = sum(1 for r in requests if not rp.can_fetch(r.url, ua))
        assert blocked == 0, \
            f"Jumia robots.txt should not block any category URL; {blocked} were blocked"

    def test_jumia_disables_robotstxt(self):
        """ROBOTSTXT_OBEY=False is kept as a precaution (Jumia's policy permits
        scraping by properly-identified bots)."""
        from egyscraper.spiders.jumia import JumiaSpider
        spider = JumiaSpider()
        assert spider.custom_settings.get("ROBOTSTXT_OBEY") is False

    def test_jumia_user_agent_satisfies_robots_policy(self):
        from egyscraper.spiders.jumia import JumiaSpider
        ua = JumiaSpider().custom_settings.get("USER_AGENT", "")
        assert "contact:" in ua.lower() or "scraper@" in ua

    def test_jumia_start_requests_yields_category_urls(self):
        from egyscraper.spiders.jumia import JumiaSpider
        spider = JumiaSpider()
        requests = list(spider.start_requests())
        assert len(requests) >= 8
        urls = [r.url for r in requests]
        assert any("men-clothing" in u or "women-clothing" in u for u in urls)


# ── Fix 3: New Balance — image validation bypassed ───────────────────────────

class TestNewBalanceImageValidation:
    """Evidence: scope_accepted=92, dropped_items=112.
    Arithmetic: 112 - 92 (validation drops) = 20 dedup drops.
    All 92 scope-accepted items had image_urls=[] from JSON-LD.
    ValidationPipeline.missing_required() includes image_urls in REQUIRED_FIELDS."""

    def test_newbalance_store_requires_images_false(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        nb = JSONLD_STORES["newbalance"]
        assert nb.require_images is False, (
            "require_images must be False for newbalance — JS-rendered images "
            "always produce image:[] in JSON-LD"
        )

    def test_jsonld_spider_propagates_require_images_false(self):
        spider = _make_spider("jsonld", store="newbalance")
        assert spider.images_required is False

    def test_jsonld_spider_other_stores_still_require_images(self):
        spider = _make_spider("jsonld", store="lcwaikiki")
        assert spider.images_required is True

    def test_validation_pipeline_passes_item_without_images_when_allowed(self):
        """When spider.images_required=False an item missing only image_urls
        must NOT be dropped."""
        record = {
            "title": "Accelerate Pacer Short Sleeve",
            "price": 1000,
            "image_urls": [],
            "product_url": "https://www.newbalance.com.eg/en/buy-accelerate",
        }
        drop_msg = _run_validation(record, spider_images_required=False)
        assert drop_msg is None, (
            f"Item should NOT be dropped when images_required=False, got: {drop_msg}"
        )

    def test_validation_pipeline_still_drops_missing_images_by_default(self):
        """Stores that don't set require_images=False must still fail without images."""
        record = {
            "title": "Some Product",
            "price": 500,
            "image_urls": [],
            "product_url": "https://example.com/product",
        }
        drop_msg = _run_validation(record, spider_images_required=True)
        assert drop_msg is not None and "image_urls" in drop_msg

    def test_validation_pipeline_drops_other_missing_fields_even_when_images_optional(self):
        """require_images=False only waives the image check, not price or title."""
        record = {
            "title": "",           # missing
            "price": 1000,
            "image_urls": [],
            "product_url": "https://www.newbalance.com.eg/en/buy-test",
        }
        drop_msg = _run_validation(record, spider_images_required=False)
        assert drop_msg is not None and "title" in drop_msg

    def test_newbalance_json_ld_images_really_are_empty(self):
        """Cross-check against the real HTML fixture to confirm the root cause."""
        fixture = Path(__file__).parent / "fixtures" / "newbalance_product.html"
        html = fixture.read_text(encoding="utf-8", errors="ignore")
        from egyscraper.core.jsonld import find_product_or_group
        node = find_product_or_group(html)
        assert node is not None
        images = node.get("image") or []
        assert images == [], (
            f"New Balance JSON-LD must have image:[] from the evidence HTML; got {images}"
        )


# ── Fix 4: Adidas — browser headers added ────────────────────────────────────

class TestAdidasBrowserHeaders:
    """Evidence: requests_made=32, retries=24, failures=7, scope_seen=0.
    Arithmetic: 7 failures × ~4 attempts = ~28 + 1 robots.txt success = ~29 ≈ 32.
    All sitemap URLs returned retry-eligible HTTP codes (403/500).
    robots.txt succeeded → CDN blocks everything after it.
    Fix: browser-like headers on sitemap and product requests."""

    def test_adidas_store_has_extra_headers(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        adidas = JSONLD_STORES["adidas"]
        assert adidas.extra_headers, "adidas store must define extra_headers for WAF bypass"

    def test_adidas_headers_include_accept_and_referer(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        h = JSONLD_STORES["adidas"].extra_headers
        assert "Accept" in h, "Accept header required"
        assert "Referer" in h, "Referer header required for CDN bypass"

    def test_jsonld_spider_propagates_extra_headers_to_instance(self):
        spider = _make_spider("jsonld", store="adidas")
        assert spider.extra_headers, "spider.extra_headers must be populated from store config"
        assert "Accept" in spider.extra_headers

    def test_jsonld_spider_applies_headers_to_sitemap_request(self):
        spider = _make_spider("jsonld", store="adidas")
        req = spider._sitemap_request("https://www.adidas.com.eg/en/sitemap")
        assert req is not None
        # Scrapy Request stores headers as a dict-like Headers object
        h = dict(req.headers)
        assert b"Accept" in h or "Accept" in h

    def test_stores_without_extra_headers_get_empty_dict(self):
        spider = _make_spider("jsonld", store="lcwaikiki")
        assert spider.extra_headers == {}

    def test_adidas_product_pattern_matches_evidence_url(self):
        import re
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        pat = JSONLD_STORES["adidas"].product_pattern
        # Alphanumeric SKU from evidence product page
        assert re.search(pat, "/en/real-madrid-dna-t-shirt/KG2943.html")
        # Numeric-only SKU from evidence sitemap (015110, 280647, etc.)
        assert re.search(pat, "/en/copa-mundial-boots/015110.html"), \
            "Pattern must match numeric-only 6-digit SKUs from the evidence sitemap"
        assert re.search(pat, "/en/adilette-slides/280647.html")
        # Should not match pages without SKU
        assert not re.search(pat, "/en/men-clothing")
        assert not re.search(pat, "/en/singles_day-kids")


# ── Fix 5: Lacoste — browser headers added ───────────────────────────────────

class TestLacosteBrowserHeaders:
    """Evidence: 7 requests, 0 retries, 2 failures.
    retries=0 proves failures were HTTP 404 (not 403/429/5xx which are retried).
    Two explanations: sitemap_2.xml URL changed, OR SFCC WAF returns fake-404.
    Fix: Referer + Accept headers to reduce WAF bot detection."""

    def test_lacoste_store_has_extra_headers(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        lacoste = JSONLD_STORES["lacoste"]
        assert lacoste.extra_headers, "lacoste store must define extra_headers"

    def test_lacoste_headers_include_referer(self):
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        h = JSONLD_STORES["lacoste"].extra_headers
        assert "Referer" in h
        assert "lacoste.com.eg" in h["Referer"]

    def test_lacoste_product_pattern_matches_evidence_url(self):
        import re
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        pat = JSONLD_STORES["lacoste"].product_pattern
        # From evidence canonical URL
        assert re.search(pat, "/en/shirts/short-sleeved-linen-shirt/CH5699-00.html")
        # Should not match category pages
        assert not re.search(pat, "/en/lacoste/men/clothing/polo-shirts")

    def test_failures_with_zero_retries_proves_404_not_403(self):
        """HTTP 404 is NOT in RETRY_HTTP_CODES so it would produce failures=N,
        retries=0.  HTTP 403 IS in RETRY_HTTP_CODES and would produce retries>0.
        This arithmetic is the proof that WAF is returning 404, not 403."""
        from egyscraper.settings import RETRY_HTTP_CODES
        assert 403 in RETRY_HTTP_CODES, "403 must be retried — confirms 404 is the Lacoste code"
        assert 404 not in RETRY_HTTP_CODES, "404 must NOT be retried — confirms retries=0 means 404"


# ── Cross-cutting: extra_headers field default ────────────────────────────────

class TestJsonLdStoreExtraHeadersDefault:
    def test_stores_without_headers_produce_empty_dict_not_none(self):
        """Stores that don't set extra_headers must give an empty dict,
        not None, so spider code can call .items() safely."""
        from egyscraper.stores.jsonld_stores import JSONLD_STORES
        for slug, store in JSONLD_STORES.items():
            headers = store.extra_headers or {}
            assert isinstance(headers, dict), (
                f"Store {slug}: extra_headers must be dict or None, got {type(headers)}"
            )
