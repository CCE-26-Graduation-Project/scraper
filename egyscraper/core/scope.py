"""Product scope classification for the fashion price comparison project.

This module is the single source of truth for deciding whether a product
belongs in this system. The project scope is Clothing and Footwear only.
Accessories, sports equipment, electronics, and home goods are rejected with
a reason code so the rejection breakdown can be reported and monitored.

Architecture
------------
* Store agnostic: no store names or platform names appear here.
* Multilingual: English and Arabic keywords are bundled together.
* Extensible: add keywords to the lists below, or add entries to
  _OUT_OF_SCOPE for new rejection buckets. A future language is just more
  entries in the keyword lists.
* Reusable: the same classify() / classify_record() functions are used by
  the ScopeFilterPipeline, the CLI audit tool, and can be called in tests
  directly.
* No double filtering: spiders yield everything; this module is the sole
  filter before export, so rejection counts are always accurate.

Scope types
-----------
clothing    T-shirts, shirts, jackets, jeans, dresses, activewear, underwear,
            swimwear, socks, tracksuits, and all other garment categories.
footwear    Sneakers, boots, sandals, heels, flats, loafers, slippers, and
            all other shoe / sole-based categories.

Rejection reasons
-----------------
accessory       Bags, belts, watches, sunglasses, jewelry, scarves, hats,
                gloves, hair accessories, wallets.
sports_equipment Dumbbells, treadmills, tents, bikes, rackets, compasses,
                 yoga mats, camping gear.
electronics     Headphones, smartwatches, fitness trackers, chargers, phones.
home_goods      Bottles, towels, furniture, kitchenware, household items.
out_of_scope    Catch-all for anything that cannot be categorised above.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .normalize import keyword_matcher

# ── In-scope keyword sets ──────────────────────────────────────────────────────
#
# Garment nouns only. Activity words ("gym", "running", "sport") are NOT
# included here because they appear on equipment too; the garment noun is
# the decisive signal. Clothing is checked before footwear.

_CLOTHING_KEYWORDS: List[str] = [
    # Tops
    "t-shirt", "tshirt", "t shirt", "tee", "polo", "shirt", "blouse",
    "top",          # "crop top", "tank top", "vest top"
    "camisole", "tank",
    # Outerwear
    "hoodie", "hooded", "sweatshirt", "sweater", "pullover", "jumper",
    "cardigan", "jacket", "coat", "blazer", "windbreaker", "parka", "puffer",
    "vest", "waistcoat", "gilet",
    # Bottoms
    "jeans", "denim", "pant", "trouser", "chino", "jogger", "sweatpant",
    "legging", "shorts", "short",
    # Full garments
    "dress", "gown", "skirt", "jumpsuit", "romper", "playsuit",
    "overall", "dungaree", "tracksuit", "co-ord",
    # Modest / traditional
    "abaya", "kaftan", "caftan", "galabeya", "jalabiya", "jalabiyya",
    "thobe", "kandura", "hijab", "khimar",
    # Underwear / base layer
    "underwear", "boxer", "brief", "lingerie", "bra", "sport bra",
    "panty", "thong", "bodice", "bodysuit",
    # Swim / active / sleep
    "swimwear", "swimsuit", "bikini", "swim trunk",
    "one piece", "one-piece",       # competitive / recreational swimsuit
    "jammer",                       # men's competitive swim brief
    "rashguard", "rash guard",      # surf / swim UV top
    "wetsuit",                      # water sport suit
    "activewear", "sportswear",
    "pajama", "pyjama", "sleepwear", "nightgown", "nightwear", "robe",
    # Socks / hosiery
    "sock", "stocking", "tights",
    # Head / modest wear (traditional garments; hijab is accepted, caps are not)
    "hijab", "khimar",
    # Style descriptors that only appear on garments (safe as standalone keywords)
    "long sleeve", "short sleeve", "sleeveless", "half sleeve",
    "crew neck", "v-neck", "v neck", "round neck", "turtleneck",
    "halter",       # halter neck / halter top
    "strapless",
    "bodycon",
    "maxi",         # maxi dress / maxi coat
    "midi",         # midi skirt / midi dress
    "wrap",         # chiffon wrap / wrap dress cover-up
    # Maternity
    "maternity",
    # Arabic clothing
    "قميص", "قمصان", "تي شيرت", "تيشيرت", "تيشرت",
    "بلوزة", "توب", "تانك", "كروب توب",
    "هودي", "هودى", "بفته بكاب",
    "سويت شيرت", "سويت", "بلوفر", "كارديجان",
    "جاكيت", "جاكت", "معطف", "بالطو", "بليزر",
    "بنطلون", "بنطال", "بنطلونات", "جينز", "دنيم",
    "شورت", "شورتات", "ليجن",
    "فستان", "فساتين", "تنورة", "جيبة", "جيبه",
    "جلابية", "جلاليب", "عباية", "كافتان",
    "ملابس داخلية", "بوكسر", "حمالة",
    "مايوه", "بيكيني",
    "ملابس رياضية", "بدلة رياضية",
    "بيجامة", "بيجاما",
    "شراب", "جوارب", "شرابات",
    "ملابس",
]

_FOOTWEAR_KEYWORDS: List[str] = [
    "shoe", "sneaker", "trainer", "footwear", "sandal", "boot",
    "slipper", "loafer", "heel", "stiletto",
    "flats", "ballet flat",   # bare "flat" is too generic (flat knit, flat cap)
    "mule", "clog", "espadrille", "moccasin",
    "athletic shoe", "running shoe", "court shoe",
    # Arabic footwear
    "حذاء", "احذية", "أحذية", "كوتشي", "سنيكرز",
    "صندل", "صنادل", "بوت", "جزمة",
    "شبشب", "خف", "كعب", "بلغة",
]

# ── Out-of-scope keyword sets ─────────────────────────────────────────────────
#
# Ordered from most specific to most general. The first bucket whose keywords
# fire is used as the rejection reason.

_OUT_OF_SCOPE: List[tuple] = [
    ("electronics", [
        "headphone", "earphone", "earbud", "earpiece", "headset",
        "smartwatch", "smart watch", "fitness tracker", "activity tracker",
        "speaker", "bluetooth speaker", "charger", "power bank",
        "cable", "phone", "smartphone", "tablet", "laptop", "camera",
        "gadget",
        # Arabic
        "سماعة", "سماعات", "ساعة ذكية", "شاحن", "هاتف",
    ]),
    ("sports_equipment", [
        "dumbbell", "barbell", "kettlebell", "weight plate", "weight rack",
        "resistance band", "treadmill", "elliptical", "exercise bike",
        "rowing machine", "pull-up bar", "yoga mat", "exercise mat",
        "jump rope", "skipping rope", "slam ball", "medicine ball",
        "football", "basketball", "volleyball", "tennis ball",
        "racket", "racquet", "badminton", "cricket bat",
        "tent", "sleeping bag", "kayak", "canoe", "paddle",
        "compass", "binocular", "fishing rod", "tackle",
        "bicycle", "bike", "skateboard", "scooter",
        "helmet", "shin guard", "knee pad", "elbow pad",
        "climbing harness", "carabiner", "hiking pole",
        "camping", "cooler", "lantern", "hydration pack",
        # Arabic
        "دمبل", "اثقال", "حبل مقاومة", "حصيرة يوغا",
        "دراجة", "خيمة", "مضرب", "كرة قدم",
        "معدات رياضية", "معدة رياضية",
    ]),
    ("home_goods", [
        "water bottle", "bottle", "tumbler", "flask", "thermos",
        "mug", "cup", "towel", "bath towel",
        "furniture", "chair", "sofa", "mattress", "pillow",
        "blanket", "cushion", "lamp", "vase", "rug", "curtain",
        "cookware", "kitchenware", "utensil",
        # Arabic
        "زجاجة مياه", "زجاجة", "منشفة", "اثاث", "طقم أكواب",
    ]),
    ("accessory", [
        "wallet", "purse", "coin purse",
        "bag", "handbag", "tote", "clutch", "crossbody",
        "backpack", "rucksack", "satchel", "duffel",
        "luggage", "suitcase", "trolley bag",
        "belt",
        "watch",                   # not "smartwatch" – that is already caught
        "jewelry", "jewellery",
        "necklace", "bracelet", "earring", "pendant", "brooch", "anklet", "ring",
        "sunglasses", "sunglass", "eyewear", "eyeglasses", "spectacle",
        "scarf", "shawl",
        "hat", "cap", "beanie", "beret", "bucket hat",
        "glove", "mitten",
        "hair clip", "hairband", "headband", "hair tie", "scrunchie",
        "keychain", "lanyard",
        # Arabic
        "محفظة", "محافظ",
        "حقيبة", "حقائب", "شنطة", "شنط",
        "حزام", "احزمة",
        "ساعة",
        "مجوهرات", "مجوهر", "عقد", "سوار", "حلق", "قلادة", "خاتم",
        "نظارة", "نظارات", "نظارة شمسية",
        "وشاح", "ايشارب", "طرحة",
        "قبعة", "قبعات",
        "قفاز", "قفازات",
        "هيرباند", "كليب شعر",
    ]),
]

# ── Precompile matchers ───────────────────────────────────────────────────────

_clothing_match = keyword_matcher(_CLOTHING_KEYWORDS)
_footwear_match = keyword_matcher(_FOOTWEAR_KEYWORDS)
_out_matchers = [
    (reason, keyword_matcher(kw)) for reason, kw in _OUT_OF_SCOPE
]


# ── Public API ────────────────────────────────────────────────────────────────

def classify(
    category: Optional[str] = None,
    title: Optional[str] = None,
    subcategory: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    breadcrumbs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Classify one product into clothing, footwear, or an out-of-scope bucket.

    Structured fields (category, subcategory, title, tags, breadcrumbs) are
    the primary signal and use the full keyword set. If the primary signal is
    inconclusive, the description is tried as a fallback using a RESTRICTED
    keyword set that excludes short ambiguous words.

    Why restrict the description? Marketing descriptions routinely contain
    non-garment uses of short keywords:
      "top"     → "trusted by top players" (tennis string)
      "short"   → "ideal for short distances" (golf)
      "heel"    → "heel-toe weighting" (putter)
      "denim"   → "Denim Clear" (goggle lens colour)
      "overall" → "overall performance" (any product)

    Stores like lablanca use single model names ("Vivienne", "Ophelia") with
    all product information in the description, so the fallback is essential
    for them. The restricted set keeps unambiguous multi-syllable garment
    nouns like "dress", "hoodie", "tracksuit", "swimsuit" while dropping the
    single ambiguous words above.
    """
    tag_text = " ".join(tags) if tags else ""
    crumb_text = " ".join(breadcrumbs) if breadcrumbs else ""
    primary = " ".join(filter(None, [category, subcategory, title, crumb_text, tag_text]))

    result = _classify_text(primary)
    if result is None and description:
        result = _classify_text_desc(description)
    if result is None:
        return {"is_supported": False, "rejection_reason": "out_of_scope"}
    return result

def classify_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract classification signals from a standard schema record and
    call classify(). This is what the pipeline calls on every item."""
    attrs = record.get("attributes") or {}
    tags = attrs.get("tags") or []
    breadcrumbs = (
        attrs.get("breadcrumbs")
        or attrs.get("breadcrumb")
        or []
    )
    if isinstance(breadcrumbs, str):
        breadcrumbs = [breadcrumbs]
    return classify(
        category=record.get("category"),
        title=record.get("title"),
        subcategory=record.get("subcategory"),
        description=record.get("description"),
        tags=list(tags),
        breadcrumbs=list(breadcrumbs),
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify_text(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Apply footwear, clothing, and out-of-scope matchers to a single text
    blob. Returns a scope dict on the first match, or None if nothing fires.

    Footwear is checked before clothing so a "dress shoe" resolves to footwear
    rather than triggering the clothing keyword "dress". Word boundaries ensure
    "boot" does not match inside "bootcut" and "tee" does not match inside
    "orienteering".
    """
    if not text or not text.strip():
        return None
    if _footwear_match(text):
        return {"is_supported": True, "scope_type": "footwear"}
    if _clothing_match(text):
        return {"is_supported": True, "scope_type": "clothing"}
    for reason, match in _out_matchers:
        if match(text):
            return {"is_supported": False, "rejection_reason": reason}
    return None

# ── Restricted keyword sets for description-only fallback ─────────────────────
#
# Short ambiguous words are excluded here because they appear constantly in
# marketing copy for non-garment products ("trusted by top players",
# "heel-toe weighting", "overall performance", "for short distances").
# Only multi-syllable unambiguous garment nouns are kept.
#
# Out-of-scope is intentionally not checked in description mode: fashion
# product descriptions often mention accessories ("pairs well with our belt")
# without the product being one.

_DESC_CLOTHING_EXCLUDE: frozenset = frozenset({
    "top", "short", "overall", "denim", "tank", "cap",
})
_DESC_FOOTWEAR_EXCLUDE: frozenset = frozenset({
    "heel",
})

_clothing_desc_match = keyword_matcher(
    [k for k in _CLOTHING_KEYWORDS if k not in _DESC_CLOTHING_EXCLUDE]
)
_footwear_desc_match = keyword_matcher(
    [k for k in _FOOTWEAR_KEYWORDS if k not in _DESC_FOOTWEAR_EXCLUDE]
)


def _classify_text_desc(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Like _classify_text but uses restricted matchers for description text."""
    if not text or not text.strip():
        return None
    if _footwear_desc_match(text):
        return {"is_supported": True, "scope_type": "footwear"}
    if _clothing_desc_match(text):
        return {"is_supported": True, "scope_type": "clothing"}
    return None
