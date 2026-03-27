import scrapy


class ProductItem(scrapy.Item):
    """Standardized product record across all supported e-commerce websites."""

    site = scrapy.Field()
    url = scrapy.Field()
    title = scrapy.Field()
    price = scrapy.Field()
    rating = scrapy.Field()
    images = scrapy.Field()
    category = scrapy.Field()
