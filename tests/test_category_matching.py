"""Regression tests for the word boundary category fix and the strict fashion
gate, both exposed by the live Decathlon crawl (a compass classified as a
t-shirt because "orienteering" contains "tee")."""

from egyscraper.core import normalize


# -- the exact defect from live data -------------------------------------
def test_orienteering_compass_not_tshirt():
    title = "BEGIN 100 BASEPLATE ORIENTEERING COMPASS"
    assert normalize.normalize_category(title) == ""  # was wrongly "t-shirts"


def test_laptop_not_tshirt():
    assert normalize.normalize_category("Gaming Laptop Stand") == ""


def test_word_boundary_keeps_real_tshirts():
    assert normalize.normalize_category("Graphic Tee") == "t-shirts"
    assert normalize.normalize_category("Crop Top") == "t-shirts"
    assert normalize.normalize_category("Men's Polo") == "t-shirts"


def test_accessories_still_match_as_words():
    assert normalize.normalize_category("Leather Belt") == "accessories"
    assert normalize.normalize_category("Wool Scarf") == "accessories"
    assert normalize.normalize_category("Accessories") == "accessories"


def test_no_false_accessory_from_substring():
    # "captain" contains "cap", "baggage" contains "bag": must not classify.
    assert normalize.normalize_category("Captain Armband") != "accessories"
    assert normalize.normalize_category("Baggage Allowance Guide") == ""


def test_arabic_still_matches_by_substring():
    assert normalize.normalize_category("تيشيرت قطن") == "t-shirts"
    assert normalize.normalize_category("حذاء جري") == "shoes"


# -- strict fashion gate --------------------------------------------------
def test_strict_drops_non_fashion():
    assert normalize.is_fashion("", "", "Orienteering Compass", strict=True) is False
    assert normalize.is_fashion("", "Tent 2 Person", strict=True) is False


def test_strict_keeps_apparel():
    assert normalize.is_fashion("", "Men's Running T-Shirt", strict=True) is True
    assert normalize.is_fashion("", "Trail Running Shoes", strict=True) is True


def test_lenient_default_unchanged():
    # Lenient mode still lets an unknown item through (no non fashion signal).
    assert normalize.is_fashion("", "Mystery Item") is True
    assert normalize.is_fashion("Electronics", "wireless headphone") is False
