"""Tests for the canonical schema helpers."""

from egyscraper.core import schema


def test_empty_product_has_all_fields():
    record = schema.empty_product()
    assert set(record.keys()) == set(schema.SCHEMA_FIELDS)


def test_empty_product_defaults():
    record = schema.empty_product()
    assert record["currency"] == "EGP"
    assert record["image_urls"] == []
    assert record["attributes"] == {}
    assert record["price"] is None


def test_ordered_preserves_schema_order():
    record = schema.empty_product()
    assert list(schema.ordered(record).keys())[: len(schema.SCHEMA_FIELDS)] == schema.SCHEMA_FIELDS


def test_ordered_keeps_unknown_keys():
    record = schema.empty_product()
    record["extra"] = 1
    assert "extra" in schema.ordered(record)


def test_missing_required_flags_blanks():
    record = schema.empty_product()
    missing = schema.missing_required(record)
    # a fresh record has no title, price, images or url
    assert set(missing) == {"title", "price", "image_urls", "product_url"}


def test_missing_required_passes_complete_record():
    record = schema.empty_product()
    record.update(
        {
            "title": "Tee",
            "price": 100.0,
            "image_urls": ["https://x/y.jpg"],
            "product_url": "https://x/p",
        }
    )
    assert schema.missing_required(record) == []
