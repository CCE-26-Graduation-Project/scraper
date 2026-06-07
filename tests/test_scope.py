"""Tests for the product scope classification layer.

Covers English, Arabic, ambiguous, mixed metadata, and missing signal cases.
All tests call the public classify() function directly so they have no I/O
dependency and run in milliseconds.
"""

import pytest
from egyscraper.core.scope import classify, classify_record


# helpers
def _accept(scope):
    assert scope["is_supported"] is True, f"expected accepted, got {scope}"
    return scope["scope_type"]


def _reject(scope):
    assert scope["is_supported"] is False, f"expected rejected, got {scope}"
    return scope["rejection_reason"]


# ── Clothing acceptance (English) ─────────────────────────────────────────────
class TestClothingEnglish:
    def test_tshirt_hyphenated(self):    assert _accept(classify(title="Men's Classic T-Shirt")) == "clothing"
    def test_tshirt_no_hyphen(self):     assert _accept(classify(title="Graphic Tshirt")) == "clothing"
    def test_tee(self):                  assert _accept(classify(title="Essential Tee")) == "clothing"
    def test_polo(self):                 assert _accept(classify(title="Polo Shirt")) == "clothing"
    def test_shirt(self):                assert _accept(classify(title="Oxford Button-Down Shirt")) == "clothing"
    def test_hoodie(self):               assert _accept(classify(title="Zip-Up Hoodie")) == "clothing"
    def test_hoodies_plural(self):       assert _accept(classify(title="Men Winter Hoodies")) == "clothing"
    def test_sweatshirt(self):           assert _accept(classify(title="Crewneck Sweatshirt")) == "clothing"
    def test_sweater(self):              assert _accept(classify(title="Knitted Sweater")) == "clothing"
    def test_jacket(self):               assert _accept(classify(title="Denim Jacket")) == "clothing"
    def test_coat(self):                 assert _accept(classify(title="Winter Coat")) == "clothing"
    def test_blazer(self):               assert _accept(classify(title="Slim Fit Blazer")) == "clothing"
    def test_jeans(self):                assert _accept(classify(title="Straight Leg Jeans")) == "clothing"
    def test_pants(self):                assert _accept(classify(title="Chino Pants")) == "clothing"
    def test_trousers(self):             assert _accept(classify(title="Slim Trousers")) == "clothing"
    def test_shorts(self):               assert _accept(classify(title="Running Shorts")) == "clothing"
    def test_dress(self):                assert _accept(classify(title="Wrap Dress")) == "clothing"
    def test_skirt(self):                assert _accept(classify(title="Mini Skirt")) == "clothing"
    def test_leggings(self):             assert _accept(classify(title="High Waist Leggings")) == "clothing"
    def test_tracksuit(self):            assert _accept(classify(title="Two Piece Tracksuit")) == "clothing"
    def test_activewear(self):           assert _accept(classify(title="Women's Activewear Set")) == "clothing"
    def test_sportswear(self):           assert _accept(classify(title="Sportswear Compression Top")) == "clothing"
    def test_underwear(self):            assert _accept(classify(title="Cotton Underwear Pack")) == "clothing"
    def test_bra(self):                  assert _accept(classify(title="Sports Bra")) == "clothing"
    def test_socks(self):                assert _accept(classify(title="Ankle Socks 3-Pack")) == "clothing"
    def test_swimsuit(self):             assert _accept(classify(title="One Piece Swimsuit")) == "clothing"
    def test_bikini(self):               assert _accept(classify(title="Triangle Bikini Top")) == "clothing"
    def test_abaya(self):                assert _accept(classify(title="Embroidered Abaya")) == "clothing"
    def test_kaftan(self):               assert _accept(classify(title="Printed Kaftan Dress")) == "clothing"
    def test_pajama(self):               assert _accept(classify(title="Flannel Pajama Set")) == "clothing"
    def test_sleepwear(self):            assert _accept(classify(title="Women's Sleepwear")) == "clothing"


# ── Footwear acceptance (English) ────────────────────────────────────────────
class TestFootwearEnglish:
    def test_sneakers(self):             assert _accept(classify(title="Running Sneakers")) == "footwear"
    def test_shoe(self):                 assert _accept(classify(title="Leather Dress Shoe")) == "footwear"
    def test_trainer(self):              assert _accept(classify(title="Mesh Trainers")) == "footwear"
    def test_boot(self):                 assert _accept(classify(title="Chelsea Boot")) == "footwear"
    def test_boots_plural(self):         assert _accept(classify(title="Ankle Boots")) == "footwear"
    def test_sandal(self):               assert _accept(classify(title="Slide Sandals")) == "footwear"
    def test_slipper(self):              assert _accept(classify(title="Fleece Slippers")) == "footwear"
    def test_loafer(self):               assert _accept(classify(title="Penny Loafers")) == "footwear"
    def test_heel(self):                 assert _accept(classify(title="Block Heel Mule")) == "footwear"
    def test_flat(self):                 assert _accept(classify(title="Ballet Flat")) == "footwear"
    def test_athletic_footwear(self):    assert _accept(classify(title="Athletic Footwear")) == "footwear"


# ── Arabic acceptance ────────────────────────────────────────────────────────
class TestArabicAcceptance:
    def test_shirt_ar(self):             assert _accept(classify(title="قميص قطن")) == "clothing"
    def test_tshirt_ar(self):            assert _accept(classify(title="تي شيرت رجالي")) == "clothing"
    def test_pants_ar(self):             assert _accept(classify(title="بنطلون رياضي")) == "clothing"
    def test_jacket_ar(self):            assert _accept(classify(title="جاكيت شتوي")) == "clothing"
    def test_dress_ar(self):             assert _accept(classify(title="فستان سهرة")) == "clothing"
    def test_shoe_ar(self):              assert _accept(classify(title="حذاء جري")) == "footwear"
    def test_sneaker_ar(self):           assert _accept(classify(title="سنيكرز رياضي")) == "footwear"
    def test_sandal_ar(self):            assert _accept(classify(title="صندل صيفي")) == "footwear"
    def test_clothes_ar(self):           assert _accept(classify(title="ملابس نوم")) == "clothing"


# ── Accessory rejection ──────────────────────────────────────────────────────
class TestAccessoryRejection:
    def test_wallet(self):               assert _reject(classify(title="Leather Wallet")) == "accessory"
    def test_bag(self):                  assert _reject(classify(title="Canvas Tote Bag")) == "accessory"
    def test_handbag(self):              assert _reject(classify(title="Quilted Handbag")) == "accessory"
    def test_backpack(self):             assert _reject(classify(title="15L Backpack")) == "accessory"
    def test_belt(self):                 assert _reject(classify(title="Leather Belt")) == "accessory"
    def test_watch(self):                assert _reject(classify(title="Analog Watch")) == "accessory"
    def test_sunglasses(self):           assert _reject(classify(title="UV400 Sunglasses")) == "accessory"
    def test_necklace(self):             assert _reject(classify(title="Gold Necklace")) == "accessory"
    def test_bracelet(self):             assert _reject(classify(title="Silver Bracelet")) == "accessory"
    def test_scarf(self):                assert _reject(classify(title="Cashmere Scarf")) == "accessory"
    def test_hat(self):                  assert _reject(classify(title="Wool Hat")) == "accessory"
    def test_cap(self):                  assert _reject(classify(title="Baseball Cap")) == "accessory"
    def test_gloves(self):               assert _reject(classify(title="Leather Gloves")) == "accessory"
    def test_hairband(self):             assert _reject(classify(title="Elastic Hairband")) == "accessory"
    def test_luggage(self):              assert _reject(classify(title="Hardshell Suitcase")) == "accessory"


# ── Arabic accessory rejection ───────────────────────────────────────────────
class TestArabicRejection:
    def test_wallet_ar(self):            assert _reject(classify(title="محفظة جلد")) == "accessory"
    def test_bag_ar(self):               assert _reject(classify(title="حقيبة يد")) == "accessory"
    def test_watch_ar(self):             assert _reject(classify(title="ساعة كلاسيك")) == "accessory"
    def test_glasses_ar(self):           assert _reject(classify(title="نظارة شمسية")) == "accessory"
    def test_scarf_ar(self):             assert _reject(classify(title="وشاح قطني")) == "accessory"
    def test_hat_ar(self):               assert _reject(classify(title="قبعة شمسية")) == "accessory"


# ── Sports equipment rejection ───────────────────────────────────────────────
class TestSportsEquipment:
    def test_dumbbell(self):             assert _reject(classify(title="20kg Dumbbell Set")) == "sports_equipment"
    def test_compass(self):              assert _reject(classify(title="BEGIN 100 BASEPLATE ORIENTEERING COMPASS")) == "sports_equipment"
    def test_yoga_mat(self):             assert _reject(classify(title="Non-Slip Yoga Mat")) == "sports_equipment"
    def test_tent(self):                 assert _reject(classify(title="2-Person Camping Tent")) == "sports_equipment"
    def test_resistance_band(self):      assert _reject(classify(title="Resistance Band Loop Set")) == "sports_equipment"
    def test_football(self):             assert _reject(classify(title="Size 5 Football")) == "sports_equipment"
    def test_racket(self):               assert _reject(classify(title="Tennis Racket")) == "sports_equipment"
    def test_bicycle(self):              assert _reject(classify(title="Mountain Bicycle")) == "sports_equipment"
    def test_arabic_sports_equip(self):  assert _reject(classify(title="معدات رياضية احترافية")) == "sports_equipment"


# ── Electronics rejection ────────────────────────────────────────────────────
class TestElectronics:
    def test_headphones(self):           assert _reject(classify(title="Noise Cancelling Headphones")) == "electronics"
    def test_earbuds(self):              assert _reject(classify(title="Wireless Earbuds")) == "electronics"
    def test_smartwatch(self):           assert _reject(classify(title="Smartwatch GPS")) == "electronics"
    def test_fitness_tracker(self):      assert _reject(classify(title="Fitness Tracker Band")) == "electronics"
    def test_arabic_headphones(self):    assert _reject(classify(title="سماعة بلوتوث")) == "electronics"


# ── Home goods rejection ─────────────────────────────────────────────────────
class TestHomeGoods:
    def test_water_bottle(self):         assert _reject(classify(title="Insulated Water Bottle")) == "home_goods"
    def test_bottle(self):               assert _reject(classify(title="Stainless Steel Bottle 500ml")) == "home_goods"
    def test_towel(self):                assert _reject(classify(title="Quick-Dry Towel")) == "home_goods"
    def test_arabic_bottle(self):        assert _reject(classify(title="زجاجة مياه رياضية")) == "home_goods"


# ── Ambiguous titles ─────────────────────────────────────────────────────────
class TestAmbiguous:
    def test_bootcut_jeans_is_clothing(self):
        # "bootcut" has no word boundary on "boot"; "jeans" fires → clothing
        assert _accept(classify(title="Bootcut Jeans")) == "clothing"

    def test_sports_bra_is_clothing(self):
        # "bra" is a clothing keyword → accepted before any sports signal
        assert _accept(classify(title="Sports Bra")) == "clothing"

    def test_watch_strap_is_accessory(self):
        # "watch" is an accessory keyword; no clothing / footwear keyword present
        assert _reject(classify(title="Watch Strap")) == "accessory"

    def test_smartwatch_is_electronics_not_accessory(self):
        # electronics rule fires before accessory; "smartwatch" is in electronics
        assert _reject(classify(title="Smartwatch with GPS")) == "electronics"

    def test_swim_trunks_is_clothing(self):
        assert _accept(classify(title="Men's Swim Trunks")) == "clothing"

    def test_yoga_pants_is_clothing(self):
        # "pant" fires clothing before "yoga" could fire sports_equipment
        assert _accept(classify(title="Women's Yoga Pants")) == "clothing"

    def test_bike_shorts_is_clothing(self):
        # "short" fires clothing before "bike" fires sports_equipment
        assert _accept(classify(title="Cycling Bike Shorts")) == "clothing"

    def test_orienteering_compass_is_sports_not_tshirt(self):
        # Core regression: "tee" must not match inside "orienteering"
        r = classify(title="BEGIN 100 BASEPLATE ORIENTEERING COMPASS")
        assert r["is_supported"] is False
        assert r["rejection_reason"] == "sports_equipment"


# ── Missing / mixed metadata ─────────────────────────────────────────────────
class TestMissingMetadata:
    def test_category_only(self):
        assert _accept(classify(category="t-shirts")) == "clothing"

    def test_category_empty_title_has_signal(self):
        assert _accept(classify(category="", title="Men's Running Shoes")) == "footwear"

    def test_tags_as_fallback(self):
        r = classify(category="", title="", tags=["hoodie", "men"])
        assert _accept(r) == "clothing"

    def test_description_uses_restricted_keywords_only(self):
        # Description fallback exists but uses a restricted keyword set.
        # Ambiguous short words like "top", "short", "heel", "denim" are
        # excluded to prevent marketing copy false-positives.
        # Unambiguous garment nouns like "dress", "hoodie", "swimsuit" still
        # work in descriptions.
        # Clothing found via description only (no primary signal):
        assert classify(title="Vivienne",
                        description="A stunning halter maxi dress with open back.")["is_supported"]
        # Ambiguous word in description does NOT trigger:
        widget_top = classify(title="Widget Pro",
                              description="Trusted by top players worldwide.")
        assert widget_top["is_supported"] is False
        # Same word in title DOES trigger (primary signal):
        top_shirt = classify(title="Crop Top White")
        assert top_shirt["is_supported"] is True

    def test_all_empty_is_rejected(self):
        r = classify(category="", title="", subcategory="", description="")
        assert r["is_supported"] is False

    def test_unknown_item_no_signal(self):
        # No recognisable signal at all → out_of_scope
        r = classify(title="Widget Pro 3000")
        assert r["is_supported"] is False
        assert r["rejection_reason"] == "out_of_scope"


# ── classify_record integration ──────────────────────────────────────────────
class TestClassifyRecord:
    def test_maps_category_and_title(self):
        record = {"category": "t-shirts", "title": "Graphic Tee",
                  "subcategory": "", "description": "", "attributes": {}}
        r = classify_record(record)
        assert r == {"is_supported": True, "scope_type": "clothing"}

    def test_reads_tags_from_attributes(self):
        record = {"category": "", "title": "", "subcategory": "",
                  "description": "", "attributes": {"tags": ["dress", "summer"]}}
        assert classify_record(record)["is_supported"] is True

    def test_rejected_record(self):
        record = {"category": "", "title": "Leather Wallet",
                  "subcategory": "", "description": "", "attributes": {}}
        r = classify_record(record)
        assert r == {"is_supported": False, "rejection_reason": "accessory"}
