"""Regression tests for normalize_category rules added after the June 2026
empty-category audit.  Every test corresponds to a real product pattern found
in the 544-product empty-category set across basiclook, gorillaoutfit,
intersport, iravin, lablanca, sigmafit, and townteam."""

from egyscraper.core.normalize import normalize_category


# ── Vests (townteam SKU-code products with subcategory/product_type) ──────────
class TestVests:
    def test_subcat_men_vests(self):
        assert normalize_category("Men Vests", "VST26WWCP28543TM1", "") == "vests"

    def test_subcat_boys_vests(self):
        assert normalize_category("Boys Vests", "VST25WWBP28544TB1", "") == "vests"

    def test_subcat_men_vest_singular(self):
        assert normalize_category("MEN VEST", "VST22AFWP28530TM1", "") == "vests"

    def test_gilet_in_title(self):
        # iravin "Ravin Men's Quilted Zip-Up Gilet"
        assert normalize_category("male vest", "Ravin Men's Quilted Zip-Up Gilet – Olive", "") == "jackets"
        # gilet is now under jackets (sleeveless quilted jacket)

    def test_vest_in_title(self):
        assert normalize_category("", "Slim Fit Vest Navy", "") == "vests"

    def test_vest_waistcoat(self):
        assert normalize_category("", "Three-Piece Suit Waistcoat", "") == "vests"


# ── Jumpsuits and rompers (lablanca model names with tag/desc) ────────────────
class TestJumpsuits:
    def test_jumpsuit_from_tag(self):
        # lablanca "Alaina" – tag "Evening Jumpsuits"
        assert normalize_category("", "Alaina", "Evening Jumpsuits") == "jumpsuits"

    def test_jumpsuit_from_description(self):
        assert normalize_category("", "Alaina", "Alaina Evening Jumpsuit in luxurious crepe") == "jumpsuits"

    def test_romper_from_description(self):
        # lablanca "Elena" – desc "the perfect romper for any occasion"
        assert normalize_category("", "Elena", "the perfect romper for any occasion") == "jumpsuits"

    def test_romper_tag(self):
        # lablanca "Elena" has tag "Rompers"
        assert normalize_category("", "Elena", "Evening Party Rompers") == "jumpsuits"

    def test_jumpsuit_explicit_title(self):
        assert normalize_category("", "Tailored Linen Jumpsuit", "") == "jumpsuits"

    def test_overalls(self):
        assert normalize_category("", "Classic Denim Overalls", "") == "jumpsuits"

    def test_dungaree(self):
        assert normalize_category("", "Short Dungaree Blue", "") == "jumpsuits"


# ── Swimwear new keywords ─────────────────────────────────────────────────────
class TestSwimwearExtended:
    def test_burkini_from_subcat(self):
        # sigmafit "Camouflage Burkini Set" – subcat "Burkini"
        assert normalize_category("Burkini", "Camouflage Burkini Set", "Burkini") == "swimwear"

    def test_burkini_in_title(self):
        assert normalize_category("", "Black Aqua Burkini Set", "Burkini") == "swimwear"

    def test_swimming_in_tag_path(self):
        # intersport Arena products tagged "Sports & Equipment/All Sports/Swimming"
        assert normalize_category("", "Arena Poolish Moulded Bonnet", "Default Category/Swimming") == "swimwear"

    def test_swim_cap_compound(self):
        assert normalize_category("", "Speedo Swim Cap Silicone", "") == "swimwear"

    def test_swim_bonnet(self):
        assert normalize_category("accessories", "Energetics Swimming Bonnet For Women", "Swimming") == "swimwear"

    def test_swim_hijab(self):
        assert normalize_category("", "Libra Ultra-Fit Swim Hijab For Women", "") == "swimwear"


# ── Bodysuits (basiclook ComfortFlex™ line) ───────────────────────────────────
class TestBodysuits:
    def test_bodysuit_in_title(self):
        assert normalize_category("", "Cut ComfortFlex™ Bodysuit", "") == "underwear"

    def test_bodysuit_from_description(self):
        # Title has no garment noun; description fallback finds "bodysuit"
        # (pipeline calls normalize_category(description) separately)
        from egyscraper.core.normalize import normalize_category
        assert normalize_category("smooth all-over bodysuit for active wear") == "underwear"

    def test_body_suit_two_words(self):
        assert normalize_category("", "Seamless Body Suit", "") == "underwear"


# ── Hip covers (gorillaoutfit) ────────────────────────────────────────────────
class TestHipCovers:
    def test_hip_cover_subcat(self):
        assert normalize_category("HIP COVER", "Flow Olive Hip Cover", "") == "activewear"

    def test_hip_cover_title(self):
        assert normalize_category("", "Flow Dark Navy Hip Cover", "women bottom") == "activewear"


# ── Style-only t-shirt titles (basiclook) ─────────────────────────────────────
class TestStyleTitles:
    def test_crew_neck_long_sleeve(self):
        assert normalize_category("Long Sleeve", "Crew Neck Long Sleeve Rib", "") == "t-shirts"

    def test_v_neck_long_sleeve(self):
        assert normalize_category("Long Sleeve", "V-Neck Long Sleeve Rib", "") == "t-shirts"

    def test_sleeveless_as_tops(self):
        assert normalize_category("", "Sleeveless Active Top", "") == "t-shirts"


# ── Pants style terms ─────────────────────────────────────────────────────────
class TestPantsStyleTerms:
    def test_straight_leg_desc(self):
        # basiclook "Straight Leg - Women" – description says "straight-leg pants"
        assert normalize_category("", "Straight Leg - Women",
                                  "straight-leg pants crafted from interlock cotton") == "pants"

    def test_wide_leg(self):
        assert normalize_category("", "Wide Leg Linen Trousers", "") == "pants"

    def test_straight_leg_title(self):
        assert normalize_category("", "Straight-Leg Chino", "") == "pants"


# ── Dresses new keywords (wraps, cover-ups, bodycon) ─────────────────────────
class TestDressesExtended:
    def test_chiffon_wrap(self):
        # intersport "Aerobird Chiffon Wrap For Women"
        assert normalize_category("", "Aerobird Chiffon Wrap For Women, Olive Green", "") == "dresses"

    def test_bodycon(self):
        assert normalize_category("", "Bodycon Mini Dress", "") == "dresses"

    def test_cover_up(self):
        assert normalize_category("", "Beach Cover-Up Kaftan", "") == "dresses"

    def test_coverup_no_hyphen(self):
        assert normalize_category("", "Swim Coverup Sarong", "") == "dresses"


# ── Description fallback for model-name stores (lablanca) ─────────────────────
class TestDescriptionFallback:
    def test_model_name_dress_from_description(self):
        # "Vivienne" – no garment noun in title, description says "maxi dress"
        assert normalize_category("", "Vivienne",
                                  "Introducing Vivienne - the halter maxi dress with open back.") == "dresses"

    def test_model_name_jumpsuit_from_description(self):
        assert normalize_category("", "Serelle",
                                  "Elevate your evening look with Serelle, the jumpsuit that "
                                  "effortlessly blends sophistication with fun.") == "jumpsuits"

    def test_model_name_gown_from_description(self):
        assert normalize_category("", "Avelina",
                                  "Avelina is an elegant evening gown crafted from delicate lace.") == "dresses"

    def test_primary_wins_over_description(self):
        # When title has a keyword, description is NOT consulted.
        # Even if description says something different, primary wins.
        cat = normalize_category("", "Classic Hoodie", "This beautiful evening dress is warm.")
        assert cat == "hoodies"  # title wins, not description

    def test_empty_description_returns_empty(self):
        assert normalize_category("", "XYZ123", "") == ""

    def test_no_false_positive_from_non_garment_desc(self):
        # Scope has filtered these out already, but confirm normalize doesn't
        # turn "top players" into a category for clearly-rejected items.
        # (These would never reach the pipeline, but good to verify.)
        assert normalize_category("", "Tennis String", "") == ""
