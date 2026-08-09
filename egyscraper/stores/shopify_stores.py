"""Registry of Shopify based stores.

Each entry is a store the generic Shopify spider can crawl with no custom
code: it only needs the origin url, a slug for output and ids, and the
currency. The ``confirmed`` flag marks stores verified against the original
prototype's working input list; the rest are strong candidates from the
target list that present as Shopify and should be verified before a full run
(visit ``<base_url>/products.json`` in a browser; a JSON product list means
it is Shopify).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ShopifyStore:
    slug: str
    base_url: str
    currency: str = "EGP"
    confirmed: bool = False
    # Optional explicit collection paths; empty means crawl the store wide
    # /products.json endpoint, which returns the full catalog on most stores.
    collections: List[str] = field(default_factory=list)


# Confirmed from the original Shopify prototype's base_urls.txt and validated by
# live crawls (each yields products through the store wide or collection path).
_CONFIRMED = [
    ShopifyStore("lablanca", "https://lablancaegypt.com", confirmed=True),
    ShopifyStore("townteam", "https://townteam.com", confirmed=True),
    ShopifyStore("iravin", "https://shop.iravin.com", confirmed=True),
    ShopifyStore("sigmafit", "https://sigmafiteg.com", confirmed=True),
    ShopifyStore("wayupsports", "https://wayupsports.com", confirmed=True),
    ShopifyStore("basiclook", "https://basiclook.com", confirmed=True),
    ShopifyStore("intersport", "https://www.intersport.com.eg", confirmed=True),
    ShopifyStore("gorillaoutfit", "https://gorillaoutfit.com", confirmed=True),
]
# Note: mitcha was previously listed here but live crawls return HTML (status
# 200) from both /products.json and /collections.json, so it is not a Shopify
# storefront. It is handled as a custom store (see stores/classification.py).

# Verified August 2026 (see brands.md): each returned a real product array
# from /products.json. Moved here from _CANDIDATES now that they're confirmed.
_CANDIDATES = [
    ShopifyStore("carinawear", "https://carinawear.com", confirmed=True),
    ShopifyStore("pinkshop", "https://pinkshopeg.com", confirmed=True),
    ShopifyStore("tiehouse", "https://tie-house.com", confirmed=True),
    ShopifyStore("youremma", "https://youremma.com", confirmed=True),
    ShopifyStore("lavitoscarf", "https://lavitoscarf.com", confirmed=True),
    # Locale prefixed Shopify Plus store; the path returns the Egypt catalog.
    ShopifyStore("aloyoga", "https://www.aloyoga.com/en-eg", confirmed=True),
]
# Note: izzyapparel and mobaco were previously listed here as Shopify
# candidates. Live verification (August 2026, see brands.md) found both
# actually serve WooCommerce (/wp-json/wc/store/products returns JSON,
# /products.json returns HTML), so they were removed. They need a
# WooCommerce spider, not this one.
#
# Also removed, verified August 2026 (see brands.md):
#   tomatostore.com   — domain expired, now a parked-domain sales page.
#   andoraeg.com      — live site, but not Shopify and not WooCommerce either
#                       (/products.json and /wp-json/wc/store/products both
#                       404); platform not yet identified.
#   americaneagle.com.eg — live site, custom platform, not Shopify.
#   accessorize.com   — Salesforce Commerce Cloud (Demandware), not Shopify.

# Verified directly against brands.md (August 2026): each entry below returned
# a real product array from /products.json during that verification pass, so
# these are trusted at the same confidence as _CONFIRMED rather than guesses.
_VERIFIED = [
    ShopifyStore("aminak", "https://aminak.net", confirmed=True),
    ShopifyStore("mixandmatch", "https://mixandmatcheg.com", confirmed=True),
    ShopifyStore("myne", "https://mynethelabel.co", confirmed=True),
    ShopifyStore("shopfufa", "https://shopfufa.com", confirmed=True),
    ShopifyStore("saqhoute", "https://saqhoute.com", confirmed=True),
    ShopifyStore("palma", "https://getpalma.com", confirmed=True),
    ShopifyStore("tajsisters", "https://tajsisters.com", confirmed=True),
    ShopifyStore("mamzi", "https://mamzistore.com", confirmed=True),
    ShopifyStore("ganubi", "https://ganubistore.com", confirmed=True),
    ShopifyStore("notfound", "https://notfoundco.com", confirmed=True),
    ShopifyStore("denjo", "https://denjo.co", confirmed=True),
    ShopifyStore("ohanna", "https://ohannaofficial.com", confirmed=True),
    ShopifyStore("psych", "https://psychonlinestore.com", confirmed=True),
    ShopifyStore("manifest", "https://mnfstwrld.com", confirmed=True),
    ShopifyStore("sahara", "https://thesahara-collection.com", confirmed=True),
    ShopifyStore("blaze", "https://blaze-eg.com", confirmed=True),
    ShopifyStore("atum", "https://atumegypt.com", confirmed=True),
    ShopifyStore("riot", "https://rioteg.com", confirmed=True),
    ShopifyStore("gymapparel", "https://gymapparel.net", confirmed=True),
    ShopifyStore("mavin", "https://mavin-wear.com", confirmed=True),
    ShopifyStore("fittribe", "https://fittribeeg.com", confirmed=True),
    ShopifyStore("libra", "https://libra-sportswear.com", confirmed=True),
    ShopifyStore("roo", "https://rooegypt.com", confirmed=True),
    ShopifyStore("papillon", "https://papillonwear.com", confirmed=True),
    ShopifyStore("lovelyland", "https://lovelylandeg.com", confirmed=True),
    # magmasportswear moved here from _CANDIDATES: same verification pass
    # confirmed it (41 products returned).
    ShopifyStore("magmasportswear", "https://magmasportswear.com", confirmed=True),
]

# Sourced from a different discovery route (August 2026): the vendor directory
# at locallyeg.com/brands, a marketplace whose own catalog only carries a
# partial selection of each vendor's products (confirmed by spot-checking —
# see brands.md "How brands were sourced"). locallyeg.com itself is not
# scraped; each vendor's own storefront below is used instead. Each entry
# returned a real product array from /products.json during verification.
_FROM_LOCALLYEG = [
    ShopifyStore("8tsh", "https://8tsh.com", confirmed=True),
    ShopifyStore("antikka", "https://antikkaeg.com", confirmed=True),
    ShopifyStore("blackedition", "https://blackeditionshop.com", confirmed=True),
    ShopifyStore("bodiz", "https://bodiz.net", confirmed=True),
    ShopifyStore("clippys", "https://clippyss.com", confirmed=True),
    ShopifyStore("dripayaa", "https://dripayaa.com", confirmed=True),
    ShopifyStore("eighties", "https://eightieseg.com", confirmed=True),
    ShopifyStore("escala", "https://escalaapparel.com", confirmed=True),
    ShopifyStore("frenchee", "https://frencheethelabel.com", confirmed=True),
    ShopifyStore("goodritual", "https://thegoodritualeg.com", confirmed=True),
    ShopifyStore("jiggyandco", "https://jiggyandco.com", confirmed=True),
    ShopifyStore("mzaco", "https://mzaco-eg.com", confirmed=True),
    ShopifyStore("noclue", "https://shop-noclue.com", confirmed=True),
    ShopifyStore("pledges", "https://pledges-eg.com", confirmed=True),
    ShopifyStore("pulp", "https://pulpeg.com", confirmed=True),
    ShopifyStore("richness", "https://richnesseg.com", confirmed=True),
    ShopifyStore("seemly", "https://seemlycollective.com", confirmed=True),
    ShopifyStore("slack", "https://slack.clothing", confirmed=True),
    ShopifyStore("svg", "https://svgsfnx.com", confirmed=True),
    ShopifyStore("theblanks", "https://theblankseg.store", confirmed=True),
    ShopifyStore("vega", "https://vegaegy.com", confirmed=True),
    ShopifyStore("virko", "https://shopvirko.com", confirmed=True),
    ShopifyStore("yonyo", "https://yonyoeg.com", confirmed=True),
    # Name match is plausible but not fully certain against locallyeg's "XC"
    # listing (storefront brand name is "Xced") — see brands.md.
    ShopifyStore("xced", "https://xced-eg.com", confirmed=True),
    # Custom domains don't resolve to a working storefront; only the
    # underlying myshopify.com subdomain is live.
    ShopifyStore("twentyseven", "https://twentysevenegy.myshopify.com", confirmed=True),
    ShopifyStore("wahm", "https://wahmeg.myshopify.com", confirmed=True),
]

# Sourced from brands_new.md (August 2026): a follow-up research round that
# mined Go Native (gonative.eg) and LOKAL (lokaleg.com) — two more Cairo
# multi-brand marketplaces — plus Egyptian fashion-media roundups, for
# brands not covered by the original Foraj list or the locallyeg batch.
# Each entry below returned a real product array from /products.json during
# verification; the marketplaces themselves are not scraped (same reasoning
# as locallyeg — partial catalogs only).
_FROM_BRANDS_NEW = [
    ShopifyStore("deckedout", "https://shopdeckedout.com", confirmed=True),
    ShopifyStore("cave", "https://caveeg.com", confirmed=True),
    ShopifyStore("zedzee", "https://shopzedzee.com", confirmed=True),
    ShopifyStore("bowline", "https://bowlinestore.com", confirmed=True),
    ShopifyStore("milvus", "https://milvus.shop", confirmed=True),
    ShopifyStore("versattire", "https://versattirecollections.com", confirmed=True),
    ShopifyStore("ctrlcairo", "https://ctrlcairo.com", confirmed=True),
    ShopifyStore("blanksandco", "https://blanksandco.com", confirmed=True),
    ShopifyStore("browntoast", "https://browntoast.co", confirmed=True),
    ShopifyStore("inyourshoe", "https://inyourshoe.com", confirmed=True),
    ShopifyStore("alcamileon", "https://alcamileonstudio.com", confirmed=True),
    ShopifyStore("rebelcairo", "https://rebelcairo.com", confirmed=True),
    ShopifyStore("basicstitches", "https://basic-stitches.com", confirmed=True),
    ShopifyStore("meroe", "https://shopmeroe.com", confirmed=True),
    ShopifyStore("sacer", "https://sacer.eco", confirmed=True),
    ShopifyStore("almah", "https://almah.org", confirmed=True),
    ShopifyStore("anjasportswear", "https://anjasportswear.com", confirmed=True),
    ShopifyStore("saltswim", "https://salt-eg.com", confirmed=True),
    ShopifyStore("juvenile", "https://juvenileeg.com", confirmed=True),
    ShopifyStore("fear2fuckup", "https://fear2fuckup.com", confirmed=True),
    ShopifyStore("rednm", "https://rednm.shop", confirmed=True),
    ShopifyStore("locco", "https://loccoeg.com", confirmed=True),
    ShopifyStore("kaicollections", "https://kaicollections.com", confirmed=True),
    ShopifyStore("bazic", "https://shopbazic.com", confirmed=True),
    # Real domain is blanckaeg.com (no dash) — brands_new.md's blancka-eg.com
    # (with dash) does not resolve.
    ShopifyStore("blancka", "https://blanckaeg.com", confirmed=True),
    ShopifyStore("sass", "https://sass-eg.shop", confirmed=True),
    ShopifyStore("fallensaints", "https://fallensaints.co", confirmed=True),
    ShopifyStore("obi", "https://obiboutique.com", confirmed=True),
    ShopifyStore("meste", "https://meste-eg.com", confirmed=True),
    ShopifyStore("callingallangels", "https://callingallangelsco.com", confirmed=True),
    ShopifyStore("riddle", "https://riddleg.com", confirmed=True),
    ShopifyStore("kntdmen", "https://kntd.store", confirmed=True),
    ShopifyStore("fourteen", "https://fourteen-eg.com", confirmed=True),
    ShopifyStore("sabeya", "https://sabeyastore.com", confirmed=True),
    ShopifyStore("aykoona", "https://aykoona.com", confirmed=True),
    ShopifyStore("blurred", "https://blurredofficial.com", confirmed=True),
    ShopifyStore("byeverland", "https://byeverland.com", confirmed=True),
    ShopifyStore("klassico", "https://klassico.co", confirmed=True),
    ShopifyStore("nastrends", "https://nastrends.com", confirmed=True),
    ShopifyStore("ordinaryproduct", "https://ordinaryproduct.com", confirmed=True),
]

SHOPIFY_STORES: Dict[str, ShopifyStore] = {
    store.slug: store for store in (
        _CONFIRMED + _VERIFIED + _FROM_LOCALLYEG + _FROM_BRANDS_NEW + _CANDIDATES
    )
}


def get_store(slug: str) -> Optional[ShopifyStore]:
    return SHOPIFY_STORES.get(slug)


def confirmed_slugs() -> List[str]:
    return [s.slug for s in SHOPIFY_STORES.values() if s.confirmed]


def all_slugs() -> List[str]:
    return list(SHOPIFY_STORES.keys())
