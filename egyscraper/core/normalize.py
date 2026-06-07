"""Cross store, multilingual normalization helpers.

Every store describes the same concepts differently and in different languages.
These functions map messy, store specific vocabulary in Arabic or English onto
a small consistent set of canonical values, so search, filtering and comparison
work uniformly across the Egyptian market.

Design for more languages: each concept is a list of (canonical, synonyms)
rules where the synonym set simply mixes languages. Adding a third language
means adding its words to the existing sets, with no code change. Matching is
plain substring matching, which works for both Latin and Arabic script.

Money is parsed to ``Decimal`` (quantized to two places) so currency never
passes through a float.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

TWO_PLACES = Decimal("0.01")

# ---------------------------------------------------------------------------
# Category normalization (ordered: specific rules before generic ones)
# ---------------------------------------------------------------------------
CATEGORIES: List[str] = [
    "t-shirts", "shirts", "hoodies", "sweatshirts", "jackets", "jeans",
    "pants", "shorts", "dresses", "skirts", "tracksuits", "jumpsuits",
    "vests", "swimwear", "hijab", "activewear", "underwear", "socks",
    "shoes", "accessories",
]

# Each rule: canonical category, then synonyms across languages.
# Rules are ordered from most specific to most general; the first match wins.
_CATEGORY_RULES: List[Tuple[str, List[str]]] = [
    ("hoodies", ["hoodie", "hooded",
                 "هودي", "هودى", "بفته بكاب"]),
    ("sweatshirts", ["sweatshirt", "sweater", "pullover", "jumper", "cardigan",
                     "سويت شيرت", "سويت", "بلوفر", "كارديجان"]),
    ("t-shirts", ["t-shirt", "tshirt", "t shirt", "tee", "polo", "tank top",
                  "tank", "crop top", "camisole", "top",
                  "long sleeve", "longsleeve", "short sleeve", "sleeveless",
                  "crew neck", "v-neck", "v neck", "round neck",
                  "تيشيرت", "تي شيرت", "تيشرت", "بولو", "توب", "تانك"]),
    ("shirts", ["shirt", "blouse",
                "قميص", "قمصان", "بلوزة"]),
    ("jackets", ["jacket", "coat", "blazer", "windbreaker", "parka", "puffer",
                 "gilet",
                 "جاكيت", "جاكت", "بالطو", "بليزر", "معطف"]),
    ("vests", ["vest", "waistcoat",
               "صدرية", "جيليه"]),
    # Jumpsuits and tracksuits BEFORE jeans/shorts so "denim overalls" and
    # "short dungaree" resolve to the garment noun, not the fabric/cut word.
    ("jumpsuits", ["jumpsuit", "romper", "playsuit", "overalls", "dungaree",
                   "جمبسوت", "بذلة"]),
    ("tracksuits", ["tracksuit", "co-ord",
                    "بدلة رياضية"]),
    ("jeans", ["jean", "denim",
               "جينز", "دنيم"]),
    ("shorts", ["short",
                "شورت", "شورتات"]),
    ("pants", ["pant", "trouser", "legging", "jogger", "chino", "cargo",
               "sweatpant",
               "straight leg", "straight-leg", "wide leg", "wide-leg",
               "بنطلون", "بنطال", "بنطلونات", "ليجن", "جوجر", "شينو", "كارجو"]),
    # Skirts before dresses: "Maxi Skirt" fires here so "maxi" in the
    # dresses rule below cannot pull it into the wrong category.
    ("skirts", ["skirt",
                "جيبة", "تنورة", "جيبه"]),
    ("dresses", ["dress", "gown", "kaftan", "abaya", "galabeya", "jalabiya", "thobe",
                 "wrap", "cover-up", "coverup", "bodycon",
                 # Length tags used standalone (e.g. lablanca tags "Maxi", "Mini").
                 # Safe because skirts runs first, so "Maxi Skirt" → skirts, not here.
                 "maxi", "midi", "mini",
                 "فستان", "فساتين", "كافتان", "عباية", "جلابية"]),
    ("swimwear", ["swimwear", "swimsuit", "bikini", "swim trunk", "one piece",
                  "one-piece", "jammer", "rashguard", "rash guard", "wetsuit",
                  "burkini", "swimming", "swim hijab", "swim cap", "swim bonnet",
                  "مايوه", "بيكيني", "بوركيني"]),
    ("hijab", ["hijab", "khimar", "headscarf",
               "حجاب", "خمار"]),
    ("shoes", ["shoe", "sneaker", "trainer", "footwear", "sandal", "boot", "slipper",
               "حذاء", "احذية", "أحذية", "كوتشي", "سنيكرز", "صندل", "بوت", "جزمة", "شبشب"]),
    ("activewear", ["activewear", "sportswear", "gym", "training", "workout",
                    "sport bra", "tights", "hip cover",
                    "رياضي", "رياضى", "جيم", "تدريب"]),
    ("underwear", ["underwear", "boxer", "brief", "lingerie", "bra", "panty",
                   "panties", "intimate", "bodysuit", "body suit",
                   "ملابس داخلية", "بوكسر", "حمالة"]),
    ("socks", ["sock",
               "شراب", "جوارب", "شرابات"]),
    # Accessories is last; positive clothing/footwear keywords always win.
    ("accessories", ["accessory", "accessories", "scarf", "hat", "cap", "belt",
                     "bag", "wallet", "sunglass", "sunglasses", "watch", "glove",
                     "beanie", "necktie", "tie",
                     "اكسسوار", "إكسسوار", "وشاح", "ايشارب", "طرحة", "قبعة",
                     "حزام", "شنطة", "حقيبة", "نظارة", "ساعة"]),
]


_NON_FASHION_TERMS: List[str] = [
    "phone", "laptop", "tablet", "charger", "headphone", "earbud", "camera",
    "television", "tv ", "refrigerator", "microwave", "blender", "vacuum",
    "furniture", "sofa", "mattress", "grocery", "snack", "beverage", "supplement",
    "tyre", "tire", "engine", "motor oil", "toy", "video game", "console",
]


def _build_matchers(rules):
    """Precompile per category matchers.

    Latin keywords use word boundary regexes so a keyword only matches a whole
    word (so "tee" matches "graphic tee" but not "orienteering", and "top"
    matches "crop top" but not "laptop"). Non Latin (Arabic) keywords keep
    plain substring matching, since word boundaries do not apply the same way
    in Arabic script.
    """
    matchers = []
    for category, keywords in rules:
        ascii_kw = sorted((k for k in keywords if k.isascii()), key=len, reverse=True)
        other_kw = [k for k in keywords if not k.isascii()]
        pattern = None
        if ascii_kw:
            # Match whole words, allowing a plural suffix so a singular keyword
            # ("shoe", "hoodie") still matches its plural ("shoes", "hoodies").
            # The word boundary still prevents matching inside another word
            # (so "tee" does not match "orienteering").
            pattern = re.compile(
                r"\b(" + "|".join(re.escape(k) for k in ascii_kw) + r")(?:s|es)?\b"
            )
        matchers.append((category, pattern, other_kw))
    return matchers


def keyword_matcher(keywords: list):
    """Return a callable(text: str) -> bool that returns True when any keyword
    in the list is found in the text.

    Latin keywords are matched on word boundaries (with optional plural suffix)
    so short words like "tee" do not match inside longer words like
    "orienteering". Non-Latin (Arabic, etc.) keywords use substring matching.

    This is the canonical matching primitive shared by the category normaliser
    and the scope filter, keeping both in sync.
    """
    ascii_kw = sorted((k for k in keywords if k.isascii()), key=len, reverse=True)
    other_kw = [k for k in keywords if not k.isascii()]
    pattern = (
        re.compile(r"\b(" + "|".join(re.escape(k) for k in ascii_kw) + r")(?:s|es)?\b")
        if ascii_kw else None
    )

    def match(text: Optional[str]) -> bool:
        if not text:
            return False
        t = text.lower()
        if pattern is not None and pattern.search(t):
            return True
        return any(k in t for k in other_kw)

    return match


_CATEGORY_MATCHERS = _build_matchers(_CATEGORY_RULES)

# Keywords excluded from description-based category matching.  These words
# generate false positives when present in marketing copy for non-garment
# products:
#   "top"           → "trusted by top players" (tennis strings)
#   "short"         → "ideal for short distances" (golf equipment)
#   "overall"       → "overall performance" (any product)
#   "denim"         → "Denim Clear" (goggle lens colour)
#   "t-shirt" set   → "includes a t-shirt" on an athletic set (the set is
#                     not itself a t-shirt)
#   activity words  → "training sessions", "workout" in treadmill/racket
#                     descriptions; assigning "activewear" then causes the
#                     scope classifier to accept equipment as clothing
#   "swimming"      → "swimming goggles High-performance swimming" —
#                     "swimming" is an activity, "swimwear"/"swimsuit" are
#                     the garment nouns (kept below)
#
# The description fallback is restricted to clear garment nouns only so that
# it recovers stores like lablanca (model names as titles, garment nouns in
# description) without creating a bypass path for fitness equipment.
_DESC_CATEGORY_EXCLUDE = frozenset({
    "top", "short", "overall", "denim",
    "t-shirt", "tshirt", "t shirt", "tee",
    "activewear", "sportswear", "training", "workout", "gym",
    "swimming",
})

_CATEGORY_DESC_MATCHERS = _build_matchers([
    (cat, [kw for kw in kws if kw.lower() not in _DESC_CATEGORY_EXCLUDE])
    for cat, kws in _CATEGORY_RULES
])


def normalize_category(*sources: Optional[str]) -> str:
    """Return a canonical category from any number of free text hints.

    Works on Arabic or English text. The first matching rule (rules are ordered
    specific before generic) wins; returns an empty string when nothing
    matches. Latin keywords match on word boundaries to avoid false positives.
    """
    haystack = " ".join(s.lower() for s in sources if s).strip()
    if not haystack:
        return ""
    for category, pattern, other_kw in _CATEGORY_MATCHERS:
        if pattern is not None and pattern.search(haystack):
            return category
        if any(k in haystack for k in other_kw):
            return category
    return ""


def normalize_category_from_description(*sources: Optional[str]) -> str:
    """Like normalize_category but safe to use on free-text descriptions.

    Uses the same rule set with a reduced keyword list that strips out words
    that routinely appear in non-garment marketing copy ("top players",
    "overall performance", "for short distances", "Denim Clear" lens colour,
    "includes a t-shirt" on a set that is not itself a t-shirt).

    Should only be called as a fallback when the structured fields (subcategory,
    title, tags) have already been tried and returned an empty string.
    """
    haystack = " ".join(s.lower() for s in sources if s).strip()
    if not haystack:
        return ""
    for category, pattern, other_kw in _CATEGORY_DESC_MATCHERS:
        if pattern is not None and pattern.search(haystack):
            return category
        if any(k in haystack for k in other_kw):
            return category
    return ""


def is_fashion(*sources: Optional[str], strict: bool = False) -> bool:
    """Decide whether an item belongs in this fashion catalog.

    Default (lenient): return False only when a clearly non fashion term is
    present and no fashion category can be inferred. Pure clothing stores pass
    easily.

    Strict: require a positive fashion category. Use this for general retailers
    (for example sporting goods stores) whose catalog is mostly non apparel, so
    a compass or a tent is excluded rather than kept with an empty category.
    """
    haystack = " ".join(s.lower() for s in sources if s).strip()
    if strict:
        return bool(normalize_category(haystack))
    if not haystack:
        return True
    if normalize_category(haystack):
        return True
    return not any(term in haystack for term in _NON_FASHION_TERMS)


# ---------------------------------------------------------------------------
# Gender normalization (Arabic and English)
# ---------------------------------------------------------------------------
_KIDS_TERMS = ["kid", "child", "boy", "girl", "infant", "toddler", "junior",
               "اطفال", "أطفال", "اولادي", "ولادي", "بناتي", "بيبي", "طفل"]
_WOMEN_TERMS_AR = ["نسائي", "نسائى", "حريمي", "حريمى", "سيدات", "ليديز"]
_MEN_TERMS_AR = ["رجالي", "رجالى", "رجال", "رجاليه"]
_UNISEX_TERMS = ["unisex", "للجنسين", "الجنسين"]


def normalize_gender(*sources: Optional[str]) -> str:
    """Map free text in Arabic or English to: men, women, unisex, kids, or ""."""
    haystack = " ".join(s.lower() for s in sources if s).strip()
    if not haystack:
        return ""
    if any(k in haystack for k in _KIDS_TERMS):
        return "kids"
    if any(u in haystack for u in _UNISEX_TERMS):
        return "unisex"
    has_men = bool(re.search(r"\b(men|man|male|mens|men's)\b", haystack)) or \
        any(t in haystack for t in _MEN_TERMS_AR)
    has_women = bool(re.search(r"\b(women|woman|female|womens|women's|ladies|lady)\b", haystack)) or \
        any(t in haystack for t in _WOMEN_TERMS_AR)
    if has_men and has_women:
        return "unisex"
    if has_women:
        return "women"
    if has_men:
        return "men"
    return ""


# ---------------------------------------------------------------------------
# Colour normalization (Arabic and English to a canonical English colour)
# ---------------------------------------------------------------------------
_COLOR_SYNONYMS: List[Tuple[str, List[str]]] = [
    ("Black", ["black", "اسود", "أسود"]),
    ("White", ["white", "ابيض", "أبيض", "أوف وايت", "off white"]),
    ("Red", ["red", "احمر", "أحمر"]),
    ("Navy", ["navy", "كحلي", "نيفي"]),
    ("Blue", ["blue", "ازرق", "أزرق", "لبني", "سماوي"]),
    ("Green", ["green", "اخضر", "أخضر"]),
    ("Olive", ["olive", "زيتي", "زيتوني"]),
    ("Khaki", ["khaki", "كاكي"]),
    ("Yellow", ["yellow", "اصفر", "أصفر"]),
    ("Gray", ["gray", "grey", "رمادي", "جراي", "رصاصي"]),
    ("Brown", ["brown", "بني"]),
    ("Beige", ["beige", "بيج"]),
    ("Pink", ["pink", "وردي", "بمبي", "روز", "زهري"]),
    ("Purple", ["purple", "بنفسجي", "موف"]),
    ("Orange", ["orange", "برتقالي"]),
    ("Gold", ["gold", "ذهبي", "دهبي"]),
    ("Silver", ["silver", "فضي"]),
    ("Maroon", ["maroon", "عنابي", "خمري"]),
]


def normalize_color(value: Optional[str]) -> str:
    """Map one colour value (Arabic or English) to a canonical English colour.

    Unknown colours are returned trimmed and title cased rather than dropped,
    so nothing is lost; recognised colours collapse to a consistent token that
    text queries and faceting can rely on.
    """
    if not value:
        return ""
    text = str(value).strip()
    lowered = text.lower()
    # Choose the recognised colour that appears earliest in the string, so a
    # value like "BLUE / WHITE" resolves to its primary colour (Blue) rather
    # than whichever canonical happens to come first in the registry.
    best_canonical = None
    best_pos = None
    for canonical, synonyms in _COLOR_SYNONYMS:
        for syn in synonyms:
            pos = lowered.find(syn)
            if pos != -1 and (best_pos is None or pos < best_pos):
                best_pos = pos
                best_canonical = canonical
    return best_canonical if best_canonical else text.title()


def normalize_colors(values: Optional[Iterable[Any]]) -> List[str]:
    """Normalize and de duplicate a list of colour values, order preserved."""
    out: List[str] = []
    seen = set()
    for v in values or []:
        c = normalize_color(v)
        if not c:
            continue
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


# ---------------------------------------------------------------------------
# Money: parse to Decimal, never float
# ---------------------------------------------------------------------------
_CURRENCY_SYMBOLS: Dict[str, str] = {
    "egp": "EGP", "le": "EGP", "l.e": "EGP", "ج.م": "EGP", "جنيه": "EGP",
    "usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR",
    "gbp": "GBP", "£": "GBP", "sar": "SAR", "aed": "AED",
}


def normalize_currency(value: Optional[str], default: str = "EGP") -> str:
    """Return an ISO style currency code from a symbol or code, else default."""
    if not value:
        return default
    key = str(value).strip().lower()
    if key in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[key]
    upper = key.upper()
    if len(upper) == 3 and upper.isalpha():
        return upper
    return default


def to_decimal(value: Any) -> Optional[Decimal]:
    """Parse a price from a number or messy string into a 2 place Decimal.

    Floats are converted via their string form to avoid binary artifacts.
    Returns None when no numeric value can be found, never a fabricated zero.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, int):
        return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if isinstance(value, float):
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

    text = str(value)
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.search(r",\d{2}$", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    try:
        return Decimal(cleaned).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


# Backwards compatible alias. parse_price now returns a Decimal.
parse_price = to_decimal


# ---------------------------------------------------------------------------
# Availability, lists, materials
# ---------------------------------------------------------------------------
def normalize_availability(in_stock: Optional[bool]) -> str:
    if in_stock is None:
        return ""
    return "in_stock" if in_stock else "out_of_stock"


def clean_list(values: Optional[Iterable[Any]]) -> List[str]:
    """De duplicate, strip and drop empties from a list of strings, order kept."""
    if not values:
        return []
    seen = set()
    out: List[str] = []
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


_MATERIAL_TERMS: List[Tuple[str, List[str]]] = [
    ("cotton", ["cotton", "قطن"]),
    ("polyester", ["polyester", "بوليستر"]),
    ("wool", ["wool", "صوف"]),
    ("silk", ["silk", "حرير"]),
    ("linen", ["linen", "كتان"]),
    ("denim", ["denim", "دنيم", "جينز"]),
    ("leather", ["leather", "جلد"]),
    ("nylon", ["nylon", "نايلون"]),
    ("viscose", ["viscose", "فيسكوز"]),
    ("spandex", ["spandex", "elastane", "lycra", "ليكرا", "ايلاستان"]),
    ("cashmere", ["cashmere", "كشمير"]),
    ("modal", ["modal", "مودال"]),
    ("acrylic", ["acrylic", "اكريليك"]),
    ("fleece", ["fleece", "فليس"]),
    ("satin", ["satin", "ساتان"]),
    ("chiffon", ["chiffon", "شيفون"]),
]


def extract_materials(*sources: Optional[str]) -> List[str]:
    """Pull recognised material names (Arabic or English) out of free text."""
    haystack = " ".join(s.lower() for s in sources if s)
    found: List[str] = []
    for canonical, synonyms in _MATERIAL_TERMS:
        if any(syn in haystack for syn in synonyms):
            found.append(canonical)
    return found
