"""Tests for deterministic product and variant id generation."""

import pytest

from egyscraper.core import ids


# -- product_id -----------------------------------------------------------
def test_same_inputs_same_id():
    assert ids.product_id("townteam", "12345") == ids.product_id("townteam", "12345")


def test_merchant_case_insensitive():
    assert ids.product_id("TownTeam", "12345") == ids.product_id("townteam", "12345")


def test_different_platform_ids_differ():
    assert ids.product_id("townteam", "1") != ids.product_id("townteam", "2")


def test_different_merchants_differ():
    assert ids.product_id("townteam", "1") != ids.product_id("mitcha", "1")


def test_hierarchy_platform_id_preferred_over_handle_and_url():
    with_pid = ids.product_id("s", platform_product_id="99", handle="h", product_url="https://s/p")
    with_handle = ids.product_id("s", handle="h", product_url="https://s/p")
    assert with_pid != with_handle


def test_handle_preferred_over_url():
    with_handle = ids.product_id("s", handle="my-handle", product_url="https://s/p")
    url_only = ids.product_id("s", product_url="https://s/p")
    assert with_handle != url_only


def test_url_fallback_canonicalised():
    a = ids.product_id("s", product_url="https://s/products/x/")
    b = ids.product_id("s", product_url="https://s/products/x?variant=9")
    assert a == b and len(a) == 64


def test_requires_merchant():
    with pytest.raises(ValueError):
        ids.product_id("", "123")


def test_requires_some_identity():
    with pytest.raises(ValueError):
        ids.product_id("s")


# -- variant_id -----------------------------------------------------------
def test_variant_barcode_preferred():
    a = ids.variant_id("pid", barcode="111", sku="AAA", size="S", color="Red", index=0)
    b = ids.variant_id("pid", barcode="111", sku="ZZZ", size="L", color="Blue", index=3)
    assert a == b  # barcode wins, other fields ignored


def test_variant_sku_used_when_no_barcode():
    a = ids.variant_id("pid", sku="AAA")
    b = ids.variant_id("pid", sku="AAA")
    assert a == b
    assert a != ids.variant_id("pid", sku="BBB")


def test_variant_size_color_fallback():
    a = ids.variant_id("pid", size="M", color="Black", index=2)
    b = ids.variant_id("pid", size="M", color="Black", index=5)
    assert a == b  # size+color identical, index ignored


def test_variant_index_last_resort():
    a = ids.variant_id("pid", index=0)
    b = ids.variant_id("pid", index=1)
    assert a != b


def test_variant_scoped_to_product():
    assert ids.variant_id("p1", sku="X") != ids.variant_id("p2", sku="X")


def test_variant_requires_product_id():
    with pytest.raises(ValueError):
        ids.variant_id("", sku="X")
