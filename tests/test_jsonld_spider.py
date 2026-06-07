"""Tests for the generic JSON LD spider, no network involved."""

import pytest

from egyscraper.spiders.jsonld import JsonLdSpider


class _Stats:
    def __init__(self):
        self.values = {}

    def inc_value(self, key, count=1, start=0):
        self.values[key] = self.values.get(key, start) + count


class _Crawler:
    def __init__(self):
        self.stats = _Stats()


class _Resp:
    def __init__(self, text, url):
        self.text = text
        self.url = url


def _spider(**kw):
    sp = JsonLdSpider(base_url="https://store.com", slug="store",
                      product_pattern=r"/product/", **kw)
    sp.crawler = _Crawler()
    return sp


SITEMAP_INDEX = """<?xml version="1.0"?>
<sitemapindex><sitemap><loc>https://store.com/sitemap_products_1.xml</loc></sitemap></sitemapindex>
"""

PRODUCT_SITEMAP = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://store.com/product/red-shirt</loc></url>
  <url><loc>https://store.com/product/blue-jeans</loc></url>
  <url><loc>https://store.com/pages/about</loc></url>
</urlset>
"""

PRODUCT_HTML = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Red Shirt","sku":"R-1",
 "offers":{"@type":"Offer","price":"199.00","priceCurrency":"EGP",
           "availability":"https://schema.org/InStock"},
 "image":"https://store.com/r.jpg","category":"Shirts"}
</script></head><body></body></html>
"""


def test_requires_base_url():
    with pytest.raises(Exception):
        JsonLdSpider()


def test_seed_targets_sitemap():
    sp = _spider()
    urls = [r.url for r in sp._initial_requests()]
    assert "https://store.com/sitemap.xml" in urls


def test_sitemap_index_followed():
    sp = _spider()
    reqs = list(sp.parse_sitemap(_Resp(SITEMAP_INDEX, "https://store.com/sitemap.xml")))
    assert len(reqs) == 1
    assert reqs[0].url == "https://store.com/sitemap_products_1.xml"
    assert reqs[0].callback == sp.parse_sitemap


def test_product_urls_dispatched_and_non_products_skipped():
    sp = _spider()
    reqs = list(sp.parse_sitemap(_Resp(PRODUCT_SITEMAP, "https://store.com/sitemap_products_1.xml")))
    urls = [r.url for r in reqs]
    assert "https://store.com/product/red-shirt" in urls
    assert "https://store.com/product/blue-jeans" in urls
    assert "https://store.com/pages/about" not in urls  # not a product url
    assert all(r.callback == sp.parse_product for r in reqs)


def test_parse_product_extracts_and_maps():
    sp = _spider()
    results = list(sp.parse_product(_Resp(PRODUCT_HTML, "https://store.com/product/red-shirt")))
    assert len(results) == 1
    record = results[0]
    assert record["title"] == "Red Shirt"
    assert record["category"] == "shirts"
    assert str(record["price"]) == "199.00"


def test_parse_product_without_jsonld_is_skipped():
    sp = _spider()
    results = list(sp.parse_product(_Resp("<html>no structured data</html>", "https://store.com/product/x")))
    assert results == []
    assert sp.crawler.stats.values.get("egyscraper/no_jsonld") == 1


# -- store registry + sitemap discovery ----------------------------------
def test_store_registry_lookup():
    from egyscraper.spiders.jsonld import JsonLdSpider
    sp = JsonLdSpider(store="defacto")
    assert sp.source == "defacto"
    assert sp.base_url == "https://defacto.com.eg"


def test_unknown_store_raises():
    from egyscraper.spiders.jsonld import JsonLdSpider
    with pytest.raises(Exception):
        JsonLdSpider(store="does-not-exist")


def test_initial_requests_include_robots_and_sitemap():
    sp = _spider()
    urls = [r.url for r in sp._initial_requests()]
    assert "https://store.com/robots.txt" in urls
    assert "https://store.com/sitemap.xml" in urls


def test_parse_robots_extracts_sitemaps():
    sp = _spider()
    robots = "User-agent: *\nDisallow: /cart\nSitemap: https://store.com/sitemap_products.xml\n"
    reqs = list(sp.parse_robots(_Resp(robots, "https://store.com/robots.txt")))
    assert any("sitemap_products.xml" in r.url for r in reqs)


def test_sitemap_not_requested_twice():
    sp = _spider()
    a = sp._sitemap_request("https://store.com/sitemap.xml")
    b = sp._sitemap_request("https://store.com/sitemap.xml")
    assert a is not None and b is None  # de duplicated


def test_errback_tries_candidate_sitemaps_once():
    sp = _spider()

    class _F:
        value = ConnectionError("x")

        class request:
            url = "https://store.com/sitemap.xml"
            meta = {"kind": "sitemap"}

    first = list(sp.on_error(_F()))
    assert len(first) > 0  # candidate sitemaps tried
    second = list(sp.on_error(_F()))
    assert second == []  # only once
