"""Tests for schema.org ProductGroup handling, using the real Decathlon
evidence fixture (a product page with a ProductGroup that varies by colour)."""

from decimal import Decimal
from pathlib import Path

import pytest

from egyscraper.core import jsonld, schema
from egyscraper.core.jsonld_mapper import map_jsonld_product

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.decathlon.eg/en/p/302873-114486-men-s-breathable-crew-neck-essential-fitness-t-shirt-mottled-grey.html"
SOURCE = "decathlon"


@pytest.fixture
def decathlon_html():
    return (FIXTURES / "decathlon_productgroup.html").read_text(encoding="utf-8")


# -- extraction -----------------------------------------------------------
def test_find_product_or_group_returns_group(decathlon_html):
    node = jsonld.find_product_or_group(decathlon_html)
    assert node is not None
    assert node.get("@type") == "ProductGroup"
    assert len(node.get("hasVariant", [])) == 2


def test_plain_find_product_still_works():
    html = ('<script type="application/ld+json">'
            '{"@type":"Product","name":"X","offers":{"price":"5","priceCurrency":"EGP"}}'
            '</script>')
    assert jsonld.find_product(html)["name"] == "X"


# -- mapping --------------------------------------------------------------
def test_group_maps_all_schema_fields(decathlon_html):
    node = jsonld.find_product_or_group(decathlon_html)
    record = map_jsonld_product(node, URL, SOURCE)
    assert set(record.keys()) >= set(schema.SCHEMA_FIELDS)


def test_group_basic_fields(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert record["title"] == "Men's Breathable Crew Neck Essential Fitness T-Shirt - Mottled Grey"
    assert record["brand"] == "DOMYOS"
    assert record["category"] == "t-shirts"
    assert record["gender"] == "men"
    assert "<" not in record["description"]


def test_group_entities_decoded(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert "&#039;" not in record["title"]      # HTML entity decoded to an apostrophe
    assert "&amp;" not in record["main_image"]   # image url entity decoded


def test_group_price_and_rating(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert record["price"] == Decimal("299.00")
    assert isinstance(record["price"], Decimal)
    assert record["currency"] == "EGP"
    assert record["availability"] == "in_stock"
    assert record["rating"] == Decimal("4.70")
    assert record["review_count"] == 10943


def test_group_variants_preserved(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert len(record["variants"]) == 2
    v = record["variants"][0]
    assert set(v.keys()) == set(schema.VARIANT_FIELDS)
    assert v["sku"] == "4adc3d6a-2594-4651-a6ad-9951c68b908b"
    assert v["color"] == "GREY"
    assert v["price"] == Decimal("299.00")
    assert v["available"] is True


def test_group_colors_normalized(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    # "GREY" -> canonical "Gray"; "BLUE / WHITE" -> first match "Blue"
    assert "Gray" in record["colors"]
    assert "Blue" in record["colors"]


def test_group_sizes_empty_when_varies_by_colour_only(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert record["sizes"] == []  # honest to the evidence


def test_group_images_collected_from_variants(decathlon_html):
    record = map_jsonld_product(jsonld.find_product_or_group(decathlon_html), URL, SOURCE)
    assert len(record["image_urls"]) >= 2
    assert record["main_image"].startswith("https://contents.mediadecathlon.com/")


def test_group_id_stable_and_deduplicates_colour_pages(decathlon_html):
    # Both colour pages carry the same ProductGroup, so both map to one id.
    node = jsonld.find_product_or_group(decathlon_html)
    a = map_jsonld_product(node, URL, SOURCE)["product_id"]
    other_colour_url = URL.replace("114486", "114494").replace("grey", "blue")
    b = map_jsonld_product(node, other_colour_url, SOURCE)["product_id"]
    assert a == b and len(a) == 64
