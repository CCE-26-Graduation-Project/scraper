"""Tests for the Shopify spider's request logic, no network involved."""

import json

import pytest

from egyscraper.spiders.shopify import ShopifySpider


class _Stats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key, count=1, start=0):
        self.values[key] = self.values.get(key, start) + count


class _Crawler:
    def __init__(self):
        self.stats = _Stats()


class _FakeResponse:
    def __init__(self, payload, base="https://store.com", page=1, mode="site",
                 url="https://store.com/products.json"):
        self.text = json.dumps(payload)
        self.url = url
        self.meta = {"base": base, "page": page, "mode": mode}


class _Failure:
    """Minimal Twisted failure stand in for errback tests."""
    def __init__(self, url, mode):
        self.value = ConnectionError("refused")

        class _Req:
            pass
        self.request = _Req()
        self.request.url = url
        self.request.meta = {"mode": mode}


def _spider():
    sp = ShopifySpider(base_url="https://store.com", slug="store")
    sp.crawler = _Crawler()
    return sp


def _full_page():
    return {"products": [
        {"id": i, "title": f"Tee {i}", "handle": f"tee-{i}", "product_type": "T-Shirts",
         "variants": [{"id": i, "price": "100", "available": True}],
         "images": [{"src": f"https://store.com/{i}.jpg"}]}
        for i in range(ShopifySpider.PAGE_LIMIT)
    ]}


# -- basics ---------------------------------------------------------------
def test_requires_store_or_base_url():
    with pytest.raises(Exception):
        ShopifySpider()


def test_start_request_targets_products_json():
    sp = _spider()
    reqs = list(sp._initial_requests())
    assert reqs[0].url == "https://store.com/products.json?limit=250&page=1"
    assert reqs[0].meta["mode"] == "site"


def test_full_page_paginates():
    sp = _spider()
    results = list(sp.parse_products(_FakeResponse(_full_page(), page=1, mode="site")))
    records = [r for r in results if isinstance(r, dict)]
    nexts = [r for r in results if not isinstance(r, dict)]
    assert len(records) == ShopifySpider.PAGE_LIMIT
    assert len(nexts) == 1 and "page=2" in nexts[0].url


def test_short_page_no_pagination():
    sp = _spider()
    page = {"products": [
        {"id": 1, "title": "Tee", "handle": "tee", "product_type": "T-Shirts",
         "variants": [{"id": 1, "price": "100", "available": True}],
         "images": [{"src": "https://store.com/1.jpg"}]}
    ]}
    results = list(sp.parse_products(_FakeResponse(page, page=1, mode="site")))
    assert all(isinstance(r, dict) for r in results)  # no follow up


def test_non_fashion_item_yielded_for_pipeline_to_filter():
    # The spider no longer runs fashion filtering; it yields every mapped
    # record. Scope classification happens in ScopeFilterPipeline so the
    # rejection is counted accurately and covered by test_scope.py.
    sp = _spider()
    page = {"products": [
        {"id": 1, "title": "Wireless Earbuds", "handle": "buds", "product_type": "Electronics",
         "tags": ["headphone"], "variants": [{"id": 1, "price": "100", "available": True}],
         "images": [{"src": "https://store.com/1.jpg"}]}
    ]}
    records = [r for r in sp.parse_products(_FakeResponse(page)) if isinstance(r, dict)]
    # Spider yields; pipeline (not tested here) would then drop via ScopeFilterPipeline.
    assert len(records) == 1
    assert records[0]["title"] == "Wireless Earbuds"


# -- collection fallback (the Mitcha fix) --------------------------------
def test_empty_site_page_triggers_collection_fallback():
    sp = _spider()
    results = list(sp.parse_products(_FakeResponse({"products": []}, page=1, mode="site")))
    assert len(results) == 1
    assert results[0].url == "https://store.com/collections.json?limit=250&page=1"
    assert sp._fellback is True


def test_non_json_site_triggers_fallback():
    sp = _spider()

    class _Bad:
        text = "<html>challenge</html>"
        url = "https://store.com/products.json"
        meta = {"base": "https://store.com", "page": 1, "mode": "site"}

    results = list(sp.parse_products(_Bad()))
    assert len(results) == 1
    assert "collections.json" in results[0].url


def test_collection_mode_empty_does_not_fallback():
    sp = _spider()
    results = list(sp.parse_products(_FakeResponse({"products": []}, page=1, mode="collection")))
    assert results == []  # no fallback when already crawling collections
    assert sp._fellback is False


def test_fallback_triggers_only_once():
    sp = _spider()
    list(sp.parse_products(_FakeResponse({"products": []}, page=1, mode="site")))
    # a second empty site page must not produce another fallback request
    second = list(sp.parse_products(_FakeResponse({"products": []}, page=1, mode="site")))
    assert second == []


def test_errback_on_site_triggers_fallback():
    sp = _spider()
    results = list(sp.on_error(_Failure("https://store.com/products.json", "site")))
    assert len(results) == 1 and "collections.json" in results[0].url


def test_errback_on_collection_no_fallback():
    sp = _spider()
    results = list(sp.on_error(_Failure("https://store.com/collections/x/products.json", "collection")))
    assert results == []


def test_parse_collections_index_yields_product_requests():
    sp = _spider()
    payload = {"collections": [{"handle": "men"}, {"handle": "women"}]}
    reqs = list(sp.parse_collections_index(_FakeResponse(payload, url="https://store.com/collections.json")))
    urls = [r.url for r in reqs]
    assert "https://store.com/collections/men/products.json?limit=250&page=1" in urls
    assert "https://store.com/collections/women/products.json?limit=250&page=1" in urls
    assert all(r.meta["mode"] == "collection" for r in reqs)
