import re
import json
from typing import Dict, List

from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule

from ecom_crawler.items import ProductItem


SITE_CONFIGS: Dict[str, Dict[str, object]] = {
    "jumia": {
        "allowed_domains": ["www.jumia.com.eg"],
        "start_urls": ["https://www.jumia.com.eg/"],
        "selectors": {
            "title": ["h1.-fs20::text", "h1::text", ".name::text"],
            "price": [".prc-dsc::text", ".-b.-ltr.-tal.-fs24::text", ".prc::text"],
            "rating": [".stars._m::text", ".-fs16.-pts::text", ".rev::text"],
            "images": ["img.-fw.-fh::attr(data-src)", "img.-fw.-fh::attr(src)", "img::attr(src)"],
            "category": ["a.cbs:nth-last-child(1)::text", ".-pbxs a::text", "a::text"],
        },
        "product_allow": [r"\.html$"],
        "category_allow": [r"/"],
        "deny": [
            r"/cart",
            r"/checkout",
            r"/account",
            r"/login",
            r"/register",
            r"/wishlist",
            r"/compare",
            r"/search",
            r"/blog",
            r"/news",
            r"/contact",
            r"\?add-to-cart=",
            r"\?filter",
            r"\?sort=",
            r"\?orderby=",
            r"\?size=",
            r"\?color=",
            r"\?price=",
            r"/customer/",
            r"/sp-",
            r"/slp/",
            r"/help",
            r"/newsletter",
            r"/about",
            r"/privacy",
            r"/terms",
        ],
    },
    "lcwaikiki": {
        "allowed_domains": ["lcwaikiki.eg"],
        "start_urls": ["https://www.lcwaikiki.eg/en-US/EG"],
        "selectors": {
            "title": ["h1.product-title::text", "h1::text"],
            "price": [".price__now::text", ".product-price::text", ".price::text"],
            "rating": [".rating-score::text", ".rating::text"],
            "images": [".product-image img::attr(src)", ".swiper-slide img::attr(src)", "img::attr(src)"],
            "category": [".breadcrumb li:last-child::text", ".breadcrumb-item:last-child::text"],
        },
        "product_allow": [r"-p-", r"/product/", r"/p/"],
        "category_allow": [r"/c/", r"/category/"],
    },
    "sigmafit": {
        "allowed_domains": ["sigmafit-eg.com"],
        "start_urls": ["https://sigmafit-eg.com/"],
        "selectors": {
            "title": ["h1.product_title::text", "h1::text"],
            "price": ["p.price .amount::text", ".price .woocommerce-Price-amount::text", ".price::text"],
            "rating": [".woocommerce-product-rating .rating::text", ".star-rating::attr(aria-label)"],
            "images": [".woocommerce-product-gallery__image img::attr(src)", "img.wp-post-image::attr(src)"],
            "category": [".posted_in a:last-child::text", ".product_meta a::text"],
        },
        "product_allow": [r"/product/"],
        "category_allow": [r"/shop/", r"/product-category/"],
    },
    "townteam": {
        "allowed_domains": ["townteam.com"],
        "start_urls": ["https://townteam.com/"],
        "selectors": {
            "title": ["h1.product_title::text", "h1::text"],
            "price": [".price .amount::text", ".price::text"],
            "rating": [".star-rating::attr(aria-label)", ".rating::text"],
            "images": [".woocommerce-product-gallery__image img::attr(src)", "img::attr(src)"],
            "category": [".posted_in a:last-child::text", ".breadcrumb li:last-child::text"],
        },
        "product_allow": [r"/product/"],
        "category_allow": [r"/shop/", r"/product-category/"],
    },
    "wayupsports": {
        "allowed_domains": ["wayupsports.com"],
        "start_urls": ["https://wayupsports.com/"],
        "selectors": {
            "title": ["h1.product_title::text", "h1::text"],
            "price": [".price .amount::text", ".price::text"],
            "rating": [".star-rating::attr(aria-label)", ".rating::text"],
            "images": [".woocommerce-product-gallery__image img::attr(src)", "img::attr(src)"],
            "category": [".posted_in a:last-child::text", ".breadcrumb li:last-child::text"],
        },
        "product_allow": [r"/product/"],
        "category_allow": [r"/shop/", r"/product-category/"],
    },
    "tiehouse": {
        "allowed_domains": ["tie-house.com"],
        "start_urls": ["https://tie-house.com/shop/"],
        "selectors": {
            "title": ["h1.product_title::text", "h1::text"],
            "price": [".price .amount::text", ".price::text"],
            "rating": [".star-rating::attr(aria-label)", ".rating::text"],
            "images": [".woocommerce-product-gallery__image img::attr(src)", "img::attr(src)"],
            "category": [".posted_in a:last-child::text", ".breadcrumb li:last-child::text"],
        },
        "product_allow": [r"/product/"],
        "category_allow": [r"/shop/", r"/product-category/"],
        "crawl_settings": {
            "CLOSESPIDER_TIMEOUT": 120,
            "CLOSESPIDER_PAGECOUNT": 300,
            "DEPTH_LIMIT": 5,
        },
    },
    "emma": {
        "allowed_domains": ["emma-sleep.com.eg"],
        "start_urls": ["https://www.emma-sleep.com.eg/"],
        "selectors": {
            "title": ["h1::text", ".product__title::text"],
            "price": [".price-item--sale::text", ".price-item--regular::text", ".price::text"],
            "rating": [".rating__caption::text", ".rating::text"],
            "images": [".product__media img::attr(src)", "img::attr(src)"],
            "category": [".breadcrumb__item:last-child::text", ".breadcrumb li:last-child::text"],
        },
        "product_allow": [r"/products/", r"/product/"],
        "category_allow": [r"/collections/"],
    },
    "defacto": {
        "allowed_domains": ["defacto.com.eg"],
        "start_urls": ["https://www.defacto.com.eg/en-eg"],
        "selectors": {
            "title": ["h1::text", ".product-name::text"],
            "price": [".sales-price::text", ".price::text"],
            "rating": [".rating::text", ".review-score::text"],
            "images": [".product-gallery img::attr(src)", "img::attr(src)"],
            "category": [".breadcrumb li:last-child::text", ".breadcrumbs li:last-child::text"],
        },
        "product_allow": [r"-p-", r"/product/", r"/p/"],
        "category_allow": [r"/c/", r"/category/"],
    },
}


class UniversalSpider(CrawlSpider):
    """Single CrawlSpider that crawls multiple e-commerce websites using per-site configs."""

    name = "universal"

    custom_settings = {
        # Fallback feed. Overridden in from_crawler to make it site-specific.
        "FEEDS": {"products.json": {"format": "json", "indent": 2, "encoding": "utf-8"}},
    }

    GLOBAL_DENY_PATTERNS = [
        r"/cart",
        r"/checkout",
        r"/account",
        r"/login",
        r"/register",
        r"/wishlist",
        r"/compare",
        r"/search",
        r"/blog",
        r"/news",
        r"/contact",
        r"\?add-to-cart=",
        r"\?filter",
        r"\?sort=",
        r"\?orderby=",
        r"\?size=",
        r"\?color=",
        r"\?price=",
    ]

    def __init__(self, site: str = "jumia", *args, **kwargs):
        if site not in SITE_CONFIGS:
            supported = ", ".join(sorted(SITE_CONFIGS.keys()))
            raise ValueError(f"Unsupported site='{site}'. Supported: {supported}")

        self.site = site
        self.site_config = SITE_CONFIGS[site]

        self.allowed_domains = self.site_config["allowed_domains"]
        self.start_urls = self.site_config["start_urls"]
        self.selectors = self.site_config["selectors"]
        self.product_allow = self.site_config["product_allow"]
        self.category_allow = self.site_config.get("category_allow", [])

        deny_patterns = self.site_config.get("deny", self.GLOBAL_DENY_PATTERNS)

        product_extractor = LinkExtractor(
            allow=self.product_allow,
            deny=deny_patterns,
            deny_extensions=(
                "jpg",
                "jpeg",
                "png",
                "gif",
                "svg",
                "webp",
                "pdf",
                "zip",
                "rar",
                "mp4",
                "mp3",
            ),
            unique=True,
        )
        category_extractor = LinkExtractor(
            allow=self.category_allow,
            deny=deny_patterns,
            deny_extensions=(
                "jpg",
                "jpeg",
                "png",
                "gif",
                "svg",
                "webp",
                "pdf",
                "zip",
                "rar",
                "mp4",
                "mp3",
            ),
            unique=True,
        )

        rules = [Rule(product_extractor, callback="parse_product", follow=True)]
        if self.category_allow:
            rules.append(Rule(category_extractor, follow=True))
        self.rules = tuple(rules)

        super().__init__(*args, **kwargs)
        self._compile_rules()

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        site = kwargs.get("site", "jumia")
        site_settings = SITE_CONFIGS.get(site, {}).get("crawl_settings", {})
        crawler.settings.set(
            "FEEDS",
            {
                f"{site}_products.json": {
                    "format": "json",
                    "indent": 2,
                    "encoding": "utf-8",
                    "overwrite": True,
                }
            },
            priority="spider",
        )
        for key, value in site_settings.items():
            crawler.settings.set(key, value, priority="spider")
        return super().from_crawler(crawler, *args, **kwargs)

    def _first_text(self, response, selector_list: List[str]) -> str:
        for selector in selector_list:
            value = response.css(selector).get()
            if value:
                clean = re.sub(r"\s+", " ", value).strip()
                if clean:
                    return clean
        return ""

    def _extract_json_ld(self, response) -> Dict[str, str]:
        data = {"title": "", "price": "", "rating": "", "images": "", "category": ""}
        scripts = response.css('script[type="application/ld+json"]::text').getall()

        for raw in scripts:
            try:
                parsed = json.loads(raw)
            except Exception:
                continue

            nodes = parsed if isinstance(parsed, list) else [parsed]
            expanded_nodes = []
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                    expanded_nodes.extend(node["@graph"])
                expanded_nodes.append(node)

            for node in expanded_nodes:
                if not isinstance(node, dict):
                    continue

                node_type = node.get("@type", "")
                if isinstance(node_type, list):
                    type_tokens = [str(token).lower() for token in node_type]
                else:
                    type_tokens = [str(node_type).lower()]
                if not any("product" in token for token in type_tokens):
                    continue

                name = str(node.get("name", "")).strip()
                offers = node.get("offers", {})
                rating = node.get("aggregateRating", {})
                image = node.get("image", "")
                category = str(node.get("category", "")).strip()

                price = ""
                if isinstance(offers, dict):
                    price = str(offers.get("price", "")).strip()
                elif isinstance(offers, list) and offers:
                    first_offer = offers[0] if isinstance(offers[0], dict) else {}
                    price = str(first_offer.get("price", "")).strip()

                rating_value = ""
                if isinstance(rating, dict):
                    rating_value = str(rating.get("ratingValue", "")).strip()

                if isinstance(image, dict):
                    content_url = image.get("contentUrl") or image.get("url") or image.get("thumbnailUrl")
                    if isinstance(content_url, list):
                        image = str(content_url[0]).strip() if content_url else ""
                    else:
                        image = str(content_url or "").strip()
                elif isinstance(image, list):
                    image = str(image[0]).strip() if image else ""
                else:
                    image = str(image).strip()

                if name and not data["title"]:
                    data["title"] = name
                if price and not data["price"]:
                    data["price"] = price
                if rating_value and not data["rating"]:
                    data["rating"] = rating_value
                if image and not data["images"]:
                    data["images"] = response.urljoin(image)
                if category and not data["category"]:
                    data["category"] = category

                if data["title"] and data["price"]:
                    return data

        return data

    def _extract_category(self, response, ld_data: Dict[str, str]) -> str:
        scripts = response.css('script[type="application/ld+json"]::text').getall()
        for raw in scripts:
            try:
                parsed = json.loads(raw)
            except Exception:
                continue

            nodes = parsed if isinstance(parsed, list) else [parsed]
            expanded_nodes = []
            for node in nodes:
                if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                    expanded_nodes.extend(node["@graph"])
                expanded_nodes.append(node)

            for node in expanded_nodes:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("@type", "")
                if isinstance(node_type, list):
                    types = [str(token).lower() for token in node_type]
                else:
                    types = [str(node_type).lower()]
                if not any("breadcrumblist" in token for token in types):
                    continue

                chain = []
                for entry in node.get("itemListElement", []) or []:
                    if not isinstance(entry, dict):
                        continue
                    item = entry.get("item", {})
                    if isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                    else:
                        name = ""
                    if not name:
                        continue
                    lower = name.lower()
                    if lower in {"home", "sell on jumia"}:
                        continue
                    chain.append(name)

                if chain:
                    return " > ".join(chain)

        fallback = self._first_text(response, self.selectors["category"])
        if fallback:
            lower = fallback.lower()
            if lower not in {"sell on jumia", "home"}:
                return fallback
        return ld_data.get("category", "")

    def _first_url(self, response, selector_list: List[str]) -> str:
        for selector in selector_list:
            value = response.css(selector).get()
            if not value:
                continue
            value = value.strip()
            if value.startswith("//"):
                return response.urljoin(f"https:{value}")
            if value.startswith("/") or value.startswith("http"):
                return response.urljoin(value)
        return ""

    def parse_start_url(self, response):
        """Parse start URL as product page if it matches product patterns."""
        if any(pattern in response.url for pattern in ["/product/", "/products/", "-p-"]):
            item = self.parse_product(response)
            if item:
                yield item

    def parse_product(self, response):
        """Extract standardized product data from a product detail page."""
        title = self._first_text(response, self.selectors["title"])
        price = self._first_text(response, self.selectors["price"])
        ld_data = self._extract_json_ld(response)

        if not title:
            title = ld_data["title"]
        if not price:
            price = ld_data["price"]

        # Integrity gate: skip empty records before pipeline.
        if not title or not price:
            return None

        item = ProductItem()
        item["site"] = self.site
        item["url"] = response.url
        item["title"] = title
        item["price"] = price
        item["rating"] = self._first_text(response, self.selectors["rating"]) or ld_data["rating"]
        item["images"] = self._first_url(response, self.selectors["images"]) or ld_data["images"]
        item["category"] = self._extract_category(response, ld_data)
        return item
