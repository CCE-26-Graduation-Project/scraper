"""Regression tests derived from real store data.

Every test in this file corresponds to a specific product that was
misclassified before the audit, and documents exactly why each classifier
decision was made or changed. Do not delete these tests: they prevent
regression to the bugs found in the June 2026 audit of 7,494 real products.
"""

from egyscraper.core.scope import classify, classify_record
from egyscraper.core.normalize import normalize_category


# ── False positives found in intersport (tennis / golf / padel equipment) ──
# All 14 were caused by the description fallback matching marketing copy.
# Removing the description fallback eliminates all of them.

class TestIntersportFalsePositives:
    """Products found exported in intersport that should have been rejected."""

    def _reject(self, title):
        r = classify(title=title)
        assert r["is_supported"] is False, (
            f"Expected rejection for '{title}' but got {r}"
        )
        return r["rejection_reason"]

    def test_tennis_string_rejected(self):
        # "trusted by top players" in description used to fire "top" keyword.
        # Description fallback removed → title has no clothing/footwear keyword.
        reason = self._reject("BABOLAT RPM BLAST 12M TENNIS STRING FOR UNISEX, BLACK")
        assert reason == "out_of_scope"

    def test_overgrip_rejected(self):
        # "at the top of your game" in description.
        self._reject("Dunlop Sac Hydramax Pro 2Pc Overgrip")

    def test_another_string_rejected(self):
        self._reject("Luxilon Alu Power 125 String - Reel")

    def test_padel_racket_rejected(self):
        self._reject("WILSON BELA SUPER TOUR PADEL BLACK")

    def test_overgrip_box_rejected(self):
        self._reject("WILSON PRO OVERGRIP 60 BOX WHITE")

    def test_golf_balls_rejected(self):
        # "overall performance" in description used to fire "overall" keyword.
        self._reject("Wilson Duo Soft 12 Golf Balls")

    def test_golf_balls_range_rejected(self):
        self._reject("Wilson Prem Range 48 White Box Golf Balls")

    def test_swim_goggles_rejected(self):
        # "Denim Clear" is a lens colour, not denim fabric.
        # Description fallback fired on "denim" colour name.
        self._reject("Arena Drive 3 Goggles For Unisex")

    def test_wristband_rejected(self):
        # Description mentioned "short" in "for short games", not shorts garment.
        self._reject("Adidas Wristband S Black-White")

    def test_golf_putter_rejected(self):
        # Description "heel-toe weighting" used to fire "heel" footwear keyword.
        self._reject("Wilson Pro Staff Sgi Mrh Iii Putter (Right Hand)")

    def test_boxing_set_rejected(self):
        self._reject("Energetics Boxing Boxing Set Junior For Kids, Black & Grey")

    def test_description_fallback_removed(self):
        # "top" is excluded from description matching so "top players" in
        # a tennis string description no longer triggers clothing.
        no_desc = classify(title="Tennis Racket")
        with_top_desc = classify(title="Tennis Racket",
                                 description="Trusted by top players worldwide.")
        assert no_desc == with_top_desc   # description adds nothing here
        assert no_desc["is_supported"] is False

    def test_description_fallback_with_unambiguous_garment_noun(self):
        # "dress" IS in the restricted description set so a product whose title
        # is only a model name is correctly accepted via description.
        r = classify(title="Vivienne",
                     description="A halter maxi dress with a high slit and open back.")
        assert r == {"is_supported": True, "scope_type": "clothing"}


# ── Hijab and swim hijab correctly classified ─────────────────────────────────
class TestHijabClassification:
    """Hijabs were normalized to 'accessories' by Shopify product_type.
    Scope correctly overrides that and accepts them as clothing.
    After the normalize fix they also get the right category."""

    def test_fitness_hijab_accepted_as_clothing(self):
        r = classify(title="Libra Fitness Hijab Light For Women")
        assert r == {"is_supported": True, "scope_type": "clothing"}

    def test_swim_hijab_accepted_as_clothing(self):
        r = classify(title="Libra Ultra-Fit Swim Hijab For Women, Navy")
        assert r == {"is_supported": True, "scope_type": "clothing"}

    def test_modesty_hijab_accepted(self):
        r = classify(title="Arena Womens Modesty Hijab Allover Head Cover For Women")
        assert r == {"is_supported": True, "scope_type": "clothing"}

    def test_hijab_normalizes_to_hijab_category(self):
        # After the normalize fix, hijab title beats the accessories product_type.
        cat = normalize_category("Accessories", "Libra Fitness Hijab Light For Women")
        assert cat == "hijab", f"Expected 'hijab' but got {repr(cat)}"


# ── Swimwear keywords now in normalize ───────────────────────────────────────
class TestSwimwearNormalize:
    def test_one_piece_swimsuit_classified(self):
        r = classify(title="Trainetic One Piece For Women, Olive")
        assert r["is_supported"] is True

    def test_jammer_classified(self):
        r = classify(title="Arena M Pwskin Carbon Glide Jammer")
        assert r["is_supported"] is True

    def test_rashguard_classified(self):
        r = classify(title="Rash Guard UV50 Long Sleeve")
        assert r["is_supported"] is True

    def test_wetsuit_classified(self):
        r = classify(title="Wetsuit 3mm Full Body")
        assert r["is_supported"] is True

    def test_swimsuit_normalize_category(self):
        assert normalize_category("", "One Piece Swimsuit") == "swimwear"
        assert normalize_category("", "Racing Jammer Men") == "swimwear"

    def test_swim_hijab_normalize_category(self):
        # A swim hijab is swimwear (worn in water), so swimwear takes
        # precedence over the hijab category. The swimwear rule includes
        # "swim hijab" as an explicit compound keyword for this reason.
        cat = normalize_category("", "Swim Hijab For Women")
        assert cat == "swimwear"


# ── Wayupsports scope stat accounting regression ─────────────────────────────
class TestScopeAccountingRatio:
    """Dedup now runs BEFORE scope so scope stats count unique products only."""

    def test_pipeline_order_dedup_before_scope(self):
        from egyscraper import settings
        pipe = settings.ITEM_PIPELINES
        dedup = pipe["egyscraper.pipelines.DeduplicationPipeline"]
        scope = pipe["egyscraper.pipelines.ScopeFilterPipeline"]
        assert dedup < scope, (
            f"Dedup ({dedup}) must run before scope ({scope}) so scope stats "
            "reflect unique products, not collection-multiplied appearances"
        )

    def test_no_inflated_accepted_count_from_duplicates(self):
        # If dedup runs before scope, a duplicate product contributes only one
        # 'seen' count. This is a property test: can't replay a full crawl here,
        # but we verify the pipeline order is correct (above) which guarantees it.
        from egyscraper import settings
        assert "egyscraper.pipelines.DeduplicationPipeline" in settings.ITEM_PIPELINES
