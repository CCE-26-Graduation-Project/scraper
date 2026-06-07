"""Tests for the JSON LD product mapper."""

from decimal import Decimal

from egyscraper.core import schema
from egyscraper.core.jsonld_mapper import map_jsonld_product

URL = "https://defacto.com.eg/p/mens-shirt-123"
SOURCE = "defacto"


def _node(**overrides):
    node = {
        "@type": "Product",
        "name": "Men's Oxford Shirt",
        "description": "<p>Classic <b>cotton</b> oxford shirt.</p>",
        "sku": "DF-OX-001",
        "gtin13": "6224000555013",
        "brand": {"name": "DeFacto"},
        "image": ["https://img/1.jpg", "https://img/2.jpg"],
        "category": "Men > Shirts",
        "offers": {
            "@type": "Offer",
            "price": "499.00",
            "priceCurrency": "EGP",
            "availability": "https://schema.org/InStock",
        },
    }
    node.update(overrides)
    return node


def test_maps_all_schema_fields():
    record = map_jsonld_product(_node(), URL, SOURCE)
    assert set(record.keys()) >= set(schema.SCHEMA_FIELDS)


def test_basic_fields():
    record = map_jsonld_product(_node(), URL, SOURCE)
    assert record["title"] == "Men's Oxford Shirt"
    assert record["brand"] == "DeFacto"
    assert record["category"] == "shirts"
    assert record["gender"] == "men"
    assert record["description"] == "Classic cotton oxford shirt."


def test_price_is_decimal_and_currency():
    record = map_jsonld_product(_node(), URL, SOURCE)
    assert record["price"] == Decimal("499.00")
    assert isinstance(record["price"], Decimal)
    assert record["currency"] == "EGP"
    assert record["availability"] == "in_stock"


def test_identifiers_captured():
    record = map_jsonld_product(_node(), URL, SOURCE)
    assert record["sku"] == "DF-OX-001"
    assert record["gtin"] == "6224000555013"
    assert record["barcode"] == "6224000555013"


def test_brand_as_plain_string():
    record = map_jsonld_product(_node(brand="Acme"), URL, SOURCE)
    assert record["brand"] == "Acme"


def test_image_as_single_string():
    record = map_jsonld_product(_node(image="https://img/only.jpg"), URL, SOURCE)
    assert record["image_urls"] == ["https://img/only.jpg"]
    assert record["main_image"] == "https://img/only.jpg"


def test_aggregate_offer_uses_low_price():
    record = map_jsonld_product(
        _node(offers={"@type": "AggregateOffer", "lowPrice": "299.00",
                      "highPrice": "599.00", "priceCurrency": "EGP"}),
        URL, SOURCE,
    )
    assert record["price"] == Decimal("299.00")


def test_offer_list_builds_variants():
    record = map_jsonld_product(
        _node(offers=[
            {"sku": "A", "price": "100.00", "priceCurrency": "EGP", "availability": "https://schema.org/InStock"},
            {"sku": "B", "price": "120.00", "priceCurrency": "EGP", "availability": "https://schema.org/OutOfStock"},
        ]),
        URL, SOURCE,
    )
    assert len(record["variants"]) == 2
    assert record["price"] == Decimal("100.00")  # lowest across offers
    by_sku = {v["sku"]: v for v in record["variants"]}
    assert by_sku["B"]["available"] is False


def test_aggregate_rating():
    record = map_jsonld_product(
        _node(aggregateRating={"ratingValue": "4.5", "reviewCount": "37"}),
        URL, SOURCE,
    )
    assert record["rating"] == Decimal("4.50")
    assert record["review_count"] == 37


def test_deterministic_id_uses_sku():
    a = map_jsonld_product(_node(), URL, SOURCE)["product_id"]
    b = map_jsonld_product(_node(), URL, SOURCE)["product_id"]
    assert a == b and len(a) == 64
