from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem


class DedupValidationPipeline:
    """Drop duplicate URLs and records missing mandatory fields."""

    def __init__(self):
        self.seen_urls = set()

    def process_item(self, item):
        adapter = ItemAdapter(item)

        url = (adapter.get("url") or "").strip()
        title = (adapter.get("title") or "").strip()
        price = (adapter.get("price") or "").strip()
        category = (adapter.get("category") or "").strip()

        if not url:
            raise DropItem("Missing product URL")
        if not title or not price:
            raise DropItem(f"Missing required fields in item: {url}")

        if url in self.seen_urls:
            raise DropItem(f"Duplicate product URL: {url}")

        image_value = adapter.get("images")
        if isinstance(image_value, list):
            images = [img.strip() for img in image_value if isinstance(img, str) and img.strip()]
        elif isinstance(image_value, str):
            images = [image_value.strip()] if image_value.strip() else []
        else:
            images = []

        adapter["images"] = images[0] if images else ""
        adapter["title"] = title
        adapter["price"] = price
        adapter["category"] = category
        adapter["rating"] = (adapter.get("rating") or "").strip()

        self.seen_urls.add(url)
        return item
