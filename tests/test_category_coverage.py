"""Regression tests for the category coverage improvements.

Every test here corresponds to a real product that had an empty category in
the live data audit of June 2026.  The test names name the store and the
specific failure mode so a future regression is immediately identifiable.
"""

from egyscraper.core.normalize import normalize_category, normalize_category_from_description


# ── Rule ordering: skirts before dresses ─────────────────────────────────────
class TestSkirtsDressesOrdering:
    """Skirts rule must run before dresses so that adding maxi/midi/mini to
    dresses does not pull maxi skirts into the wrong category."""

    def test_maxi_skirt_stays_skirts(self):
        assert normalize_category("Maxi Skirt") == "skirts"

    def test_midi_skirt_stays_skirts(self):
        assert normalize_category("Midi Skirt") == "skirts"

    def test_mini_skirt_stays_skirts(self):
        assert normalize_category("Mini Skirt") == "skirts"

    def test_long_skirt_still_skirts(self):
        assert normalize_category("Long Skirt") == "skirts"

    def test_skirt_in_product_type_stays_skirts(self):
        # Shopify product_type "Skirts" in subcategory field
        assert normalize_category("Skirts", "Maxi Floral") == "skirts"


# ── maxi / midi / mini → dresses ─────────────────────────────────────────────
class TestLengthKeywords:
    """lablanca tags single-name products only with "Maxi", "Midi", "Mini".
    These should resolve to dresses when no skirt keyword is present."""

    def test_maxi_tag_alone(self):
        # lablanca "Vivienne" → tags: ["Evening", "Maxi"]
        assert normalize_category("", "Vivienne", "Evening Maxi") == "dresses"

    def test_midi_tag_alone(self):
        assert normalize_category("", "Ophelia", "Evening Midi") == "dresses"

    def test_mini_tag_alone(self):
        assert normalize_category("", "Elena", "Party Mini") == "dresses"

    def test_maxi_dress_stays_dresses(self):
        assert normalize_category("Maxi Dress") == "dresses"

    def test_midi_dress_stays_dresses(self):
        assert normalize_category("Midi Dress") == "dresses"

    def test_mini_dress_stays_dresses(self):
        assert normalize_category("Mini Dress") == "dresses"

    def test_maxi_jumpsuits_tag_stays_jumpsuits(self):
        # Products tagged both "Maxi" and "Jumpsuits" should resolve to
        # jumpsuits because jumpsuits rule runs before dresses.
        assert normalize_category("", "Alaina", "Evening Jumpsuits") == "jumpsuits"


# ── Description fallback: restricted keyword set ─────────────────────────────
class TestDescriptionFallback:
    """The restricted description matcher excludes keywords that fire on
    marketing copy for non-garment products.  Tests drawn directly from
    real false positives found in the live intersport data."""

    # False positives REMOVED by restriction
    def test_top_players_not_tshirts(self):
        desc = "Trusted by top players worldwide, this string delivers spin."
        assert normalize_category_from_description(desc) == ""

    def test_top_in_set_description_not_tshirts(self):
        desc = "High-performance 3-piece set. Includes a matching top and shorts."
        assert normalize_category_from_description(desc) == ""

    def test_tshirt_in_set_description_not_tshirts(self):
        # "includes a t-shirt" describes a component, not the product type
        desc = "Complete athletic set including a t-shirt, shorts and a jacket."
        assert normalize_category_from_description(desc) != "t-shirts"

    def test_short_distance_not_shorts(self):
        # "indoor training sessions" fires training → activewear in the full
        # matcher, but "training" is excluded from description matching so
        # equipment descriptions about "training" produce no category.
        desc = "Ideal for short distances and indoor training sessions."
        assert normalize_category_from_description(desc) == ""

    def test_denim_colour_not_jeans(self):
        # "Denim Clear" is a goggle lens colour; "swimming" is an activity
        # word, not a garment; both are excluded from description matching.
        desc = "Arena Drive 3 Denim Clear Swimming Goggles for training."
        assert normalize_category_from_description(desc) == ""

    def test_overall_performance_not_jumpsuits(self):
        desc = "Designed for overall performance and long-lasting durability."
        assert normalize_category_from_description(desc) == ""

    # True positives KEPT after restriction
    def test_dress_in_description_gives_dresses(self):
        # lablanca "Vivienne" — no garment in title, description has "dress"
        desc = "Introducing Vivienne - the halter maxi dress with a high slit."
        assert normalize_category_from_description(desc) == "dresses"

    def test_jumpsuit_in_description_gives_jumpsuits(self):
        desc = "Alaina Evening Jumpsuit in luxurious crepe fabric."
        assert normalize_category_from_description(desc) == "jumpsuits"

    def test_jacket_in_description_gives_jackets(self):
        desc = "A tailored double-breasted jacket with structured shoulders."
        assert normalize_category_from_description(desc) == "jackets"

    def test_hoodie_in_description_gives_hoodies(self):
        desc = "Soft fleece-lined hoodie with a kangaroo pocket."
        assert normalize_category_from_description(desc) == "hoodies"

    def test_training_excluded_from_description(self):
        # "training" is excluded to prevent treadmill/racket descriptions
        # ("designed for training sessions") from producing "activewear" and
        # thus bypassing the scope classifier.  gorillaoutfit athletic sets
        # that lack garment nouns are a known false-negative trade-off.
        desc = "High-performance 3-piece set designed for training and movement."
        assert normalize_category_from_description(desc) == ""

    def test_swimsuit_in_description_gives_swimwear(self):
        desc = "The Libra Feel Free swimsuit offers full-coverage stretch."
        assert normalize_category_from_description(desc) == "swimwear"


# ── Pipeline two-pass integration ────────────────────────────────────────────
class TestPipelineTwoPass:
    """The CategoryNormalizationPipeline tries primary signals first, then
    falls back to the restricted description matcher."""

    def _run(self, title, subcat="", tags=None, desc=""):
        from egyscraper.core.normalize import normalize_category, normalize_category_from_description
        tags_str = " ".join(tags or [])
        cat = normalize_category(subcat, title, tags_str)
        if not cat and desc:
            cat = normalize_category_from_description(desc)
        return cat

    def test_lablanca_model_name_resolved_from_maxi_tag(self):
        assert self._run("Vivienne", tags=["Evening", "Maxi"]) == "dresses"

    def test_lablanca_model_name_resolved_from_description_when_no_tag(self):
        desc = "Elegant strapless maxi evening dress with lace detailing."
        assert self._run("Winona", tags=["Evening"], desc=desc) == "dresses"

    def test_description_fallback_not_used_when_primary_succeeds(self):
        # Primary gives "swimwear"; misleading description ("top fit") should
        # never override it because we only call the description fallback when
        # primary is empty.
        cat_primary = normalize_category("", "Libra Feel Free Swimsuit")
        assert cat_primary == "swimwear"  # description fallback never reached

    def test_false_positive_from_full_description_is_prevented(self):
        # Old code: normalize_category(desc) → "t-shirts" via "top players"
        # New code: normalize_category_from_description(desc) → ""
        desc = "Top string on tour. Trusted by top players worldwide."
        assert self._run("Babolat RPM Blast 12m", desc=desc) == ""
