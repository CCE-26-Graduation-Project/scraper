"""Classification of every target store by technology stack.

This is the planning artifact that drives which extraction technique each
store needs. It maps the 40 targets to a best guess platform and the
recommended extraction source, following the priority order:

    public API > mobile API > GraphQL > embedded JSON > JSON LD >
    server rendered HTML > browser automation

Important: platform guesses for stores not yet built are exactly that,
guesses, and carry a ``confidence`` of "verify". They must be checked against
the live site before a spider is written. Confirmed Shopify stores (verified
via the original prototype) are marked "confirmed". Nothing here is treated
as fact by the running code; it is documentation to guide implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class StoreProfile:
    domain: str
    platform: str          # best guess platform / commerce engine
    source: str            # recommended extraction source from the priority order
    status: str            # implemented | candidate | todo
    confidence: str        # confirmed | likely | verify
    notes: str = ""


# status meanings:
#   implemented  a working spider exists (generic Shopify spider covers these)
#   candidate    presents as a supported platform, spider works once verified
#   todo         needs its own spider, technique noted below
STORE_PROFILES: List[StoreProfile] = [
    # --- Shopify, covered by the generic spider --------------------------
    StoreProfile("lablancaegypt.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("townteam.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("shop.iravin.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("sigmafiteg.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("wayupsports.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("mitcha.com", "Custom (not Shopify)", "unknown until inspected", "todo", "verify",
                 "Live crawl returns HTML for products.json and collections.json, so it is "
                 "not Shopify. Needs a product page and the Network XHR calls to identify the path."),
    StoreProfile("basiclook.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("intersport.com.eg", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("gorillaoutfit.com", "Shopify", "products.json", "implemented", "confirmed"),
    StoreProfile("carinawear.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("tomatostore.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("magmasportswear.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("pinkshopeg.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("tie-house.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("youremma.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("izzyapparel.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("mobaco.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("lavitoscarf.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("andoraeg.com", "Shopify", "products.json", "candidate", "likely"),
    StoreProfile("aloyoga.com/en-eg", "Shopify Plus", "products.json", "candidate", "verify",
                 "Likely Shopify Plus; region path may need a locale prefix."),
    StoreProfile("americaneagle.com.eg", "Shopify", "products.json", "candidate", "verify"),
    StoreProfile("accessorize.com", "Shopify", "products.json", "candidate", "verify"),

    # --- Marketplaces, dedicated spiders, strict fashion filtering --------
    StoreProfile("jumia.com.eg", "Custom marketplace", "embedded JSON / HTML", "todo", "verify",
                 "Catalog API plus JSON LD on product pages; filter to fashion category tree."),
    StoreProfile("noon.com/egypt-en", "Custom marketplace", "mobile/public API", "todo", "verify",
                 "Catalog API returns JSON; restrict to apparel categories."),
    StoreProfile("amazon.com.eg", "Amazon", "mobile API / HTML", "todo", "verify",
                 "Hardest target; heavy anti bot. Scope to fashion nodes only."),

    # --- Large international, own commerce engines, often anti bot --------
    StoreProfile("zara.com/eg", "Inditex (custom)", "public API", "todo", "verify",
                 "Inditex exposes a structured product API per region/category."),
    StoreProfile("pullandbear.com/eg", "Inditex (custom)", "public API", "todo", "verify"),
    StoreProfile("shop.mango.com/eg", "Mango (custom)", "embedded JSON", "todo", "verify",
                 "Hydration payload in page; prefer over rendered HTML."),
    StoreProfile("eg.hm.com", "H&M (custom)", "public API", "todo", "verify",
                 "H&M region API returns category JSON."),
    StoreProfile("nike.com/eg", "Nike (custom)", "public API", "todo", "verify",
                 "Nike product feed API by region; aggressive rate limits."),
    StoreProfile("adidas.com.eg", "Salesforce Commerce", "embedded JSON / API", "todo", "verify"),
    StoreProfile("newbalance.com.eg", "Salesforce Commerce", "embedded JSON / API", "todo", "verify"),
    StoreProfile("lacoste.com.eg", "Salesforce Commerce", "embedded JSON / API", "todo", "verify"),
    StoreProfile("footlocker.com.eg", "Custom", "embedded JSON / API", "todo", "verify"),
    StoreProfile("decathlon.eg", "Custom (PrestaShop)", "JSON LD (ProductGroup)", "implemented", "confirmed",
                 "Product pages embed a schema.org ProductGroup varying by colour; verified "
                 "from a real product page. Run: scrapy crawl jsonld -a store=decathlon"),
    StoreProfile("maxfashion.com/eg", "Landmark (custom)", "public API", "todo", "verify"),
    StoreProfile("defacto.com.eg", "Custom / Next.js", "JSON LD", "candidate", "verify",
                 "Generic jsonld spider; verify sitemap url and product url pattern."),
    StoreProfile("lcwaikiki.eg", "Custom", "JSON LD", "candidate", "verify",
                 "Generic jsonld spider; verify sitemap url and product url pattern."),
    StoreProfile("dabchy.com.eg", "Custom marketplace", "API / HTML", "todo", "verify",
                 "Second hand fashion marketplace."),
]


def by_status() -> Dict[str, List[StoreProfile]]:
    groups: Dict[str, List[StoreProfile]] = {}
    for profile in STORE_PROFILES:
        groups.setdefault(profile.status, []).append(profile)
    return groups


def summary() -> str:
    groups = by_status()
    lines = [f"{len(STORE_PROFILES)} target stores classified:"]
    for status in ("implemented", "candidate", "todo"):
        items = groups.get(status, [])
        lines.append(f"  {status}: {len(items)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
