"""Tests for the CLIP embedding text builder."""

from egyscraper.core.embedding_text import MAX_WORDS, build_embedding_text
from egyscraper.core.schema import empty_product
from egyscraper.core.shopify import map_shopify_product


def _record(**overrides):
    r = empty_product()
    r.update(overrides)
    return r


def test_contains_key_attributes():
    text = build_embedding_text(
        _record(
            gender="men",
            category="hoodies",
            brand="Town Team",
            title="Oversized Cotton Hoodie",
            colors=["Black", "Olive"],
            material=["cotton"],
            description="Heavyweight cotton hoodie with a relaxed fit.",
        )
    )
    lowered = text.lower()
    for needle in ["men", "hoodies", "town team", "oversized cotton hoodie", "black", "cotton"]:
        assert needle in lowered


def test_respects_word_budget():
    long_desc = "lorem ipsum " * 200
    text = build_embedding_text(_record(title="Tee", category="t-shirts", description=long_desc))
    assert len(text.split()) <= MAX_WORDS


def test_title_survives_long_description():
    long_desc = "filler " * 200
    text = build_embedding_text(
        _record(title="Distinctive Title Token", category="shirts", description=long_desc)
    )
    # The discriminative title must never be truncated away by boilerplate.
    assert "Distinctive Title Token" in text


def test_no_dangling_labels_when_fields_empty():
    text = build_embedding_text(_record(title="Plain Tee"))
    assert "color" not in text.lower()
    assert "material" not in text.lower()
    assert "by" not in text.lower().split()


def test_deterministic():
    r = _record(title="Tee", category="t-shirts", colors=["Red"])
    assert build_embedding_text(r) == build_embedding_text(r)


def test_works_on_real_mapped_product(hoodie):
    record = map_shopify_product(hoodie, "https://townteam.com", "townteam")
    text = build_embedding_text(record)
    assert text and len(text.split()) <= MAX_WORDS
    assert "hoodie" in text.lower()
