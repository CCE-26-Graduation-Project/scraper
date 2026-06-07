"""Scrapy item mirroring the canonical schema.

Spiders yield plain dicts built from core.schema.empty_product; this item makes
the schema explicit for editors and linters and is kept in sync by the assert
below.
"""

import scrapy

from .core.schema import SCHEMA_FIELDS


class ProductItem(scrapy.Item):
    product_id = scrapy.Field()
    source = scrapy.Field()
    vendor = scrapy.Field()
    brand = scrapy.Field()
    brand_normalized = scrapy.Field()
    title = scrapy.Field()
    description = scrapy.Field()
    category = scrapy.Field()
    subcategory = scrapy.Field()
    gender = scrapy.Field()
    price = scrapy.Field()
    original_price = scrapy.Field()
    currency = scrapy.Field()
    availability = scrapy.Field()
    sku = scrapy.Field()
    barcode = scrapy.Field()
    gtin = scrapy.Field()
    rating = scrapy.Field()
    review_count = scrapy.Field()
    image_urls = scrapy.Field()
    main_image = scrapy.Field()
    product_url = scrapy.Field()
    material = scrapy.Field()
    colors = scrapy.Field()
    sizes = scrapy.Field()
    variants = scrapy.Field()
    attributes = scrapy.Field()
    content_hash = scrapy.Field()
    source_updated_at = scrapy.Field()
    first_seen = scrapy.Field()
    last_seen = scrapy.Field()
    scraped_at = scrapy.Field()


assert set(ProductItem.fields.keys()) == set(SCHEMA_FIELDS), (
    "ProductItem fields are out of sync with core.schema.SCHEMA_FIELDS"
)
