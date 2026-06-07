"""Tests for the multilingual normalization helpers."""

from decimal import Decimal

from egyscraper.core import normalize


# -- category: English ----------------------------------------------------
def test_category_hoodie():
    assert normalize.normalize_category("Hoodies", "men winter") == "hoodies"


def test_category_specific_beats_generic():
    assert normalize.normalize_category("Sweatshirt") == "sweatshirts"


def test_category_from_title_only():
    assert normalize.normalize_category("", "", "Slim Fit Denim Jeans") == "jeans"


def test_category_tank_top_now_classifies():
    assert normalize.normalize_category("Tank Top") == "t-shirts"


def test_category_shoes():
    assert normalize.normalize_category("Running Sneakers") == "shoes"


def test_category_unknown_returns_empty():
    assert normalize.normalize_category("Mystery Box") == ""


# -- category: Arabic -----------------------------------------------------
def test_category_arabic_tshirt():
    assert normalize.normalize_category("تيشيرت قطن") == "t-shirts"


def test_category_arabic_dress():
    assert normalize.normalize_category("فستان سواريه") == "dresses"


def test_category_arabic_jacket():
    assert normalize.normalize_category("جاكيت شتوي") == "jackets"


# -- fashion gate ---------------------------------------------------------
def test_is_fashion_true_for_clothing():
    assert normalize.is_fashion("T-Shirts", "cotton tee") is True


def test_is_fashion_true_for_arabic_clothing():
    assert normalize.is_fashion("فستان") is True


def test_is_fashion_false_for_electronics():
    assert normalize.is_fashion("Electronics", "wireless headphone") is False


# -- gender: English ------------------------------------------------------
def test_gender_women():
    assert normalize.normalize_gender("women dress") == "women"


def test_gender_men():
    assert normalize.normalize_gender("mens shirt") == "men"


def test_gender_both_is_unisex():
    assert normalize.normalize_gender("men and women") == "unisex"


def test_gender_kids():
    assert normalize.normalize_gender("boys t-shirt") == "kids"


# -- gender: Arabic -------------------------------------------------------
def test_gender_arabic_men():
    assert normalize.normalize_gender("قميص رجالي") == "men"


def test_gender_arabic_women():
    assert normalize.normalize_gender("فستان حريمي") == "women"


def test_gender_arabic_kids():
    assert normalize.normalize_gender("تيشيرت اطفال") == "kids"


def test_gender_unknown_empty():
    assert normalize.normalize_gender("cotton tee") == ""


# -- colours: English and Arabic -----------------------------------------
def test_color_english_canonical():
    assert normalize.normalize_color("BLACK") == "Black"


def test_color_arabic_to_english():
    assert normalize.normalize_color("أحمر") == "Red"
    assert normalize.normalize_color("اسود") == "Black"


def test_color_unknown_titlecased():
    assert normalize.normalize_color("turquoise melange") == "Turquoise Melange"


def test_colors_dedup_across_languages():
    # English "black" and Arabic "اسود" both collapse to canonical Black.
    assert normalize.normalize_colors(["black", "اسود", "Red"]) == ["Black", "Red"]


# -- money: Decimal -------------------------------------------------------
def test_price_returns_decimal():
    assert normalize.to_decimal("799.00") == Decimal("799.00")
    assert isinstance(normalize.to_decimal("799"), Decimal)


def test_price_quantized_two_places():
    assert normalize.to_decimal("10") == Decimal("10.00")
    assert str(normalize.to_decimal("10")) == "10.00"


def test_price_with_currency_text():
    assert normalize.to_decimal("EGP 1,299.50") == Decimal("1299.50")


def test_price_european_format():
    assert normalize.to_decimal("1.299,50") == Decimal("1299.50")


def test_price_float_no_binary_artifacts():
    # 0.1 + 0.2 style drift must not appear.
    assert normalize.to_decimal(19.99) == Decimal("19.99")


def test_price_empty_is_none():
    assert normalize.to_decimal("") is None
    assert normalize.to_decimal(None) is None


def test_parse_price_alias():
    assert normalize.parse_price("50") == Decimal("50.00")


# -- currency, lists, materials ------------------------------------------
def test_currency_symbol():
    assert normalize.normalize_currency("LE") == "EGP"


def test_clean_list_dedup_and_strip():
    assert normalize.clean_list([" S ", "s", "M", ""]) == ["S", "M"]


def test_extract_materials_english_and_arabic():
    mats = normalize.extract_materials("100% cotton", "قطن وحرير")
    assert "cotton" in mats and "silk" in mats


def test_availability():
    assert normalize.normalize_availability(True) == "in_stock"
    assert normalize.normalize_availability(False) == "out_of_stock"
    assert normalize.normalize_availability(None) == ""
