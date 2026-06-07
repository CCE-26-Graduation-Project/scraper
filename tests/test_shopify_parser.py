"""Tests for the variant aware Shopify product mapper."""

from decimal import Decimal

from egyscraper.core import schema
from egyscraper.core.shopify import map_shopify_product

BASE = "https://townteam.com"
SOURCE = "townteam"


def test_maps_all_schema_fields(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert set(record.keys()) >= set(schema.SCHEMA_FIELDS)


def test_basic_fields(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert record["title"] == "Oversized Cotton Hoodie"
    assert record["source"] == "townteam"
    assert record["vendor"] == "Town Team"
    assert record["brand_normalized"] == "town team"
    assert record["category"] == "hoodies"
    assert record["gender"] == "men"


def test_prices_are_decimal(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert record["price"] == Decimal("799.00")
    assert isinstance(record["price"], Decimal)
    assert record["original_price"] == Decimal("999.00")


def test_product_url_from_handle(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert record["product_url"] == "https://townteam.com/products/oversized-cotton-hoodie"


def test_deterministic_id_stable(hoodie):
    a = map_shopify_product(hoodie, BASE, SOURCE)["product_id"]
    b = map_shopify_product(hoodie, BASE, SOURCE)["product_id"]
    assert a == b and len(a) == 64


# -- variant preservation (the headline fix) ------------------------------
def test_variants_preserved_not_collapsed(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert len(record["variants"]) == 3


def test_variant_fields_present(hoodie):
    v = map_shopify_product(hoodie, BASE, SOURCE)["variants"][0]
    assert set(v.keys()) == set(schema.VARIANT_FIELDS)
    assert v["sku"] == "TT-HOOD-S-BLK"
    assert v["barcode"] == "6224000000011"
    assert v["size"] == "S"
    assert v["color"] == "Black"
    assert v["price"] == Decimal("799.00")
    assert v["available"] is True


def test_variant_level_price_differs_from_product_price(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    olive = [v for v in record["variants"] if v["color"] == "Olive"][0]
    assert olive["price"] == Decimal("849.00")     # preserved
    assert record["price"] == Decimal("799.00")    # product roll up is the min


def test_variant_availability_per_size(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    by_sku = {v["sku"]: v["available"] for v in record["variants"]}
    assert by_sku["TT-HOOD-S-BLK"] is True
    assert by_sku["TT-HOOD-M-BLK"] is False  # this size is out of stock


def test_variant_ids_deterministic_and_unique(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    ids = [v["variant_id"] for v in record["variants"]]
    assert len(set(ids)) == 3
    again = [v["variant_id"] for v in map_shopify_product(hoodie, BASE, SOURCE)["variants"]]
    assert ids == again


# -- identifier roll ups --------------------------------------------------
def test_multi_variant_product_has_no_ambiguous_identifier(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    # three different skus and barcodes, so the product level value is null
    assert record["sku"] is None
    assert record["barcode"] is None


def test_single_variant_rolls_up_identifiers(dress):
    record = map_shopify_product(dress, "https://lablancaegypt.com", "lablanca")
    assert record["sku"] == "LB-DRESS-OS-RED"
    assert record["barcode"] == "6224000999013"
    assert record["gtin"] == "6224000999013"  # 13 digit barcode is a GTIN


# -- rollups, colours, materials -----------------------------------------
def test_colours_normalized_and_deduped(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert record["colors"] == ["Black", "Olive"]


def test_sizes_collected(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert set(record["sizes"]) == {"S", "M"}  # from the variants present


def test_materials_extracted(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert "cotton" in record["material"]


def test_description_html_stripped(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert "<" not in record["description"]
    assert "100% cotton" in record["description"]


def test_source_updated_at_captured(hoodie):
    record = map_shopify_product(hoodie, BASE, SOURCE)
    assert record["source_updated_at"] == "2026-05-20T10:00:00Z"


def test_dress_gender_and_category(dress):
    record = map_shopify_product(dress, "https://lablancaegypt.com", "lablanca")
    assert record["category"] == "dresses"
    assert record["gender"] == "women"


def test_shoes_category(shoes):
    record = map_shopify_product(shoes, "https://magmasportswear.com", "magma")
    assert record["category"] == "shoes"
    assert len(record["variants"]) == 3
