import scrapy
import json
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


class ShopifyProductsSpider(scrapy.Spider):
    name = "shopify_products"
    # allowed_domains = ["townteam.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 0.5,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5,
        "AUTOTHROTTLE_MAX_DELAY": 5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
    }

    base_url = ""
    first = True

    # --------------------------------------------------
    # Read collection URLs from file
    # --------------------------------------------------
    def start_requests(self):
        with open("collections.txt", "r", encoding="utf-8") as f:
            
            for line in f:
                if self.first:
                    self.base_url = line.strip()
                    self.first = False
                else:
                    url = line.strip()
                    if url:
                        yield scrapy.Request(
                            url=url,
                            callback=self.parse_collection
                        )

    # --------------------------------------------------
    # Collection → products.json
    # --------------------------------------------------
    def parse_collection(self, response):
        json_url = response.url.rstrip("/") + "/products.json?limit=250&page=1"

        yield scrapy.Request(
            url=json_url,
            callback=self.parse_collection_json,
            meta={"collection_url": response.url}
        )

    # --------------------------------------------------
    # Parse products.json + paginate
    # --------------------------------------------------
    def parse_collection_json(self, response):
        data = json.loads(response.text)
        products = data.get("products", [])

        for product in products:
            yield {
                "product_id": product.get("id"),
                "title": product.get("title"),
                "handle": product.get("handle"),
                "url": f"{self.base_url}/products/{product.get('handle')}",
                "vendor": product.get("vendor"),
                "product_type": product.get("product_type"),
                "tags": product.get("tags"),
                "price": (
                    product["variants"][0]["price"]
                    if product.get("variants")
                    else None
                ),
                "available": (
                    product["variants"][0]["available"]
                    if product.get("variants")
                    else None
                ),
                "images": [
                    img.get("src") for img in product.get("images", [])
                ],
                "collection_url": response.meta["collection_url"],
            }

        if len(products) == 250:
            parsed = urlparse(response.url)
            qs = parse_qs(parsed.query)
            current_page = int(qs.get("page", ["1"])[0])
            qs["page"] = [str(current_page + 1)]

            next_url = urlunparse(
                parsed._replace(query=urlencode(qs, doseq=True))
            )

            yield scrapy.Request(
                url=next_url,
                callback=self.parse_collection_json,
                meta=response.meta
            )
