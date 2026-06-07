"""Tests for the JSON LD extraction helpers."""

from egyscraper.core import jsonld

_HTML_SIMPLE = """
<html><head>
<script type="application/ld+json">
{"@type": "Product", "name": "Cotton Tee", "offers": {"price": "299.00"}}
</script>
</head><body></body></html>
"""

_HTML_GRAPH = """
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"BreadcrumbList"},
  {"@type":"Product","name":"Graph Tee"}
]}
</script>
"""

_HTML_TYPE_LIST = """
<script type="application/ld+json">
{"@type":["Product","Clothing"],"name":"Multi Type Tee"}
</script>
"""

_HTML_MALFORMED = """
<script type="application/ld+json">{ this is not valid json }</script>
<script type="application/ld+json">{"@type":"Product","name":"Good One"}</script>
"""


def test_extract_blocks_returns_parsed():
    blocks = jsonld.extract_jsonld_blocks(_HTML_SIMPLE)
    assert len(blocks) == 1
    assert blocks[0]["name"] == "Cotton Tee"


def test_find_product_simple():
    product = jsonld.find_product(_HTML_SIMPLE)
    assert product and product["name"] == "Cotton Tee"


def test_find_product_in_graph():
    product = jsonld.find_product(_HTML_GRAPH)
    assert product and product["name"] == "Graph Tee"


def test_find_product_type_as_list():
    product = jsonld.find_product(_HTML_TYPE_LIST)
    assert product and product["name"] == "Multi Type Tee"


def test_malformed_block_is_skipped_not_fatal():
    product = jsonld.find_product(_HTML_MALFORMED)
    assert product and product["name"] == "Good One"


def test_no_product_returns_none():
    assert jsonld.find_product("<html><body>nothing</body></html>") is None


def test_empty_input():
    assert jsonld.extract_jsonld_blocks("") == []
    assert jsonld.find_product("") is None
