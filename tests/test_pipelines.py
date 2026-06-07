"""Tests for the item pipeline stages."""

from decimal import Decimal

import pytest
from scrapy.exceptions import DropItem

from egyscraper.core.schema import empty_product
from egyscraper.pipelines import (
    CategoryNormalizationPipeline,
    ChangeTrackingPipeline,
    CleaningPipeline,
    DeduplicationPipeline,
    PriceNormalizationPipeline,
    ValidationPipeline,
)


class _Stats:
    def inc_value(self, *_):
        pass


class _Crawler:
    stats = _Stats()


class _Spider:
    crawler = _Crawler()


SPIDER = _Spider()


def _record(**overrides):
    record = empty_product()
    record.update(overrides)
    return record


# -- cleaning -------------------------------------------------------------
def test_cleaning_trims_and_dedupes_lists():
    record = _record(title="  Tee  ", image_urls=[" a ", "a", "b"])
    out = CleaningPipeline().process_item(record, SPIDER)
    assert out["title"] == "Tee"
    assert out["image_urls"] == ["a", "b"]


def test_cleaning_normalizes_colours():
    out = CleaningPipeline().process_item(_record(colors=["اسود", "Red"]), SPIDER)
    assert out["colors"] == ["Black", "Red"]


def test_cleaning_preserves_variants():
    variants = [{"sku": "X", "size": "S"}]
    out = CleaningPipeline().process_item(_record(variants=variants), SPIDER)
    assert out["variants"] == variants


def test_cleaning_fills_brand_normalized():
    out = CleaningPipeline().process_item(_record(brand="Town Team"), SPIDER)
    assert out["brand_normalized"] == "town team"


# -- price ----------------------------------------------------------------
def test_price_pipeline_to_decimal():
    out = PriceNormalizationPipeline().process_item(
        _record(price="EGP 799.00", original_price="999"), SPIDER
    )
    assert out["price"] == Decimal("799.00")
    assert isinstance(out["price"], Decimal)
    assert out["original_price"] == Decimal("999.00")


def test_price_pipeline_normalizes_variants():
    record = _record(variants=[{"price": "799.00", "compare_at_price": None, "original_price": "999"}])
    out = PriceNormalizationPipeline().process_item(record, SPIDER)
    assert out["variants"][0]["price"] == Decimal("799.00")
    assert isinstance(out["variants"][0]["price"], Decimal)


def test_price_pipeline_drops_invalid_original():
    out = PriceNormalizationPipeline().process_item(
        _record(price=Decimal("800.00"), original_price=Decimal("700.00")), SPIDER
    )
    assert out["original_price"] is None


# -- category backfill ----------------------------------------------------
def test_category_pipeline_backfills():
    out = CategoryNormalizationPipeline().process_item(
        _record(category="", title="Cotton Hoodie", subcategory="Hoodies"), SPIDER
    )
    assert out["category"] == "hoodies"


def test_category_pipeline_arabic():
    out = CategoryNormalizationPipeline().process_item(
        _record(category="", title="فستان سهرة"), SPIDER
    )
    assert out["category"] == "dresses"


# -- validation -----------------------------------------------------------
def test_validation_drops_incomplete():
    with pytest.raises(DropItem):
        ValidationPipeline().process_item(_record(title="Tee"), SPIDER)


def test_validation_passes_complete():
    record = _record(title="Tee", price=Decimal("100.00"), image_urls=["x.jpg"], product_url="https://x/p")
    out = ValidationPipeline().process_item(record, SPIDER)
    assert out["title"] == "Tee"


# -- change tracking ------------------------------------------------------
def test_change_tracking_stamps_hash_and_timestamps():
    record = _record(title="Tee", scraped_at="2026-06-01T00:00:00+00:00")
    out = ChangeTrackingPipeline().process_item(record, SPIDER)
    assert out["content_hash"] and len(out["content_hash"]) == 64
    assert out["last_seen"] == "2026-06-01T00:00:00+00:00"
    assert out["first_seen"] == "2026-06-01T00:00:00+00:00"


def test_change_tracking_keeps_existing_first_seen():
    record = _record(scraped_at="2026-06-01T00:00:00+00:00", first_seen="2026-01-01T00:00:00+00:00")
    out = ChangeTrackingPipeline().process_item(record, SPIDER)
    assert out["first_seen"] == "2026-01-01T00:00:00+00:00"


# -- deduplication --------------------------------------------------------
def test_dedup_drops_repeated_id():
    pipe = DeduplicationPipeline()
    pipe.process_item(_record(product_id="abc"), SPIDER)
    with pytest.raises(DropItem):
        pipe.process_item(_record(product_id="abc"), SPIDER)


def test_dedup_allows_distinct_ids():
    pipe = DeduplicationPipeline()
    pipe.process_item(_record(product_id="a"), SPIDER)
    out = pipe.process_item(_record(product_id="b"), SPIDER)
    assert out["product_id"] == "b"
