"""Edge case coverage and boundary behaviour."""

from decimal import Decimal

from egyscraper.core import normalize
from egyscraper.core.shopify import map_shopify_product

BASE = "https://store.com"
SOURCE = "store"


# -- Shopify mapper boundaries -------------------------------------------
def test_product_with_no_variants_has_null_price():
    product = {"id": 1, "title": "No Variant Tee", "handle": "x", "variants": [], "images": []}
    record = map_shopify_product(product, BASE, SOURCE)
    assert record["price"] is None
    assert record["variants"] == []
    assert record["availability"] == "out_of_stock"


def test_product_with_no_images_has_empty_main_image():
    product = {
        "id": 2, "title": "Tee", "handle": "y",
        "variants": [{"id": 1, "price": "100", "available": True}], "images": [],
    }
    record = map_shopify_product(product, BASE, SOURCE)
    assert record["image_urls"] == []
    assert record["main_image"] == ""


def test_tags_as_comma_string():
    product = {
        "id": 3, "title": "Tee", "handle": "z", "tags": "men, summer, cotton",
        "variants": [{"id": 1, "price": "100", "available": True}],
        "images": [{"src": "https://store.com/a.jpg"}],
    }
    record = map_shopify_product(product, BASE, SOURCE)
    assert record["attributes"]["tags"] == ["men", "summer", "cotton"]
    assert "cotton" in record["material"]


def test_missing_handle_falls_back_to_base_url():
    product = {"id": 4, "title": "Tee", "variants": [{"id": 1, "price": "1", "available": True}], "images": []}
    record = map_shopify_product(product, BASE, SOURCE)
    assert record["product_url"] == BASE


def test_compare_at_below_price_is_discarded():
    product = {
        "id": 5, "title": "Tee", "handle": "h",
        "variants": [{"id": 1, "price": "500", "compare_at_price": "400", "available": True}],
        "images": [{"src": "https://store.com/a.jpg"}],
    }
    record = map_shopify_product(product, BASE, SOURCE)
    assert record["original_price"] is None
    assert record["variants"][0]["original_price"] is None


# -- money boundaries -----------------------------------------------------
def test_zero_price_parses_to_zero():
    assert normalize.to_decimal("0.00") == Decimal("0.00")


def test_negative_looking_price_keeps_magnitude():
    assert normalize.to_decimal("-50") == Decimal("50.00")


def test_price_with_arabic_currency_word():
    assert normalize.to_decimal("299 ج.م") == Decimal("299.00")


# -- multilingual classification (previously known gaps, now fixed) -------
def test_arabic_category_now_classifies():
    assert normalize.normalize_category("تيشيرت قطن") == "t-shirts"


def test_tank_top_now_classifies():
    assert normalize.normalize_category("tank top") == "t-shirts"
