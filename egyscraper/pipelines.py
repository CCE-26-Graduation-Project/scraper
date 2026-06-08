"""Item pipelines.

Items flow through these stages in priority order (lowest number first):

  200 CleaningPipeline             trim, coerce lists, normalise the record shape
  300 PriceNormalizationPipeline   parse product and variant prices to Decimal
  400 CategoryNormalizationPipeline backfill category, gender and colours
  450 DeduplicationPipeline        drop records whose product_id was already seen
  460 ScopeFilterPipeline          accept clothing/footwear; reject everything else
  470 ValidationPipeline           drop records missing a required field
  480 ChangeTrackingPipeline       stamp content_hash, first_seen, last_seen
  900 ExportPipeline               write to products.jsonl + health report

Deduplication runs BEFORE scope so scope statistics count unique products.
When a store is crawled via many overlapping collections the same product
appears once per collection; without dedup-first the scope seen/accepted
counters are inflated by the duplication factor (observed 20x for
wayupsports). Dedup-first means scope_total_discovered in the crawl report
always equals the number of unique products the spider discovered.
  900 ExportPipeline               stream to JSONL and (optionally) a JSON array

Scrapy 2.13 stopped passing a ``spider`` argument to pipeline methods, so the
methods take an optional ``spider`` (kept for older Scrapy) and read runtime
context from ``self.crawler``, which is saved in from_crawler. A single bad
item raises DropItem and is logged; it never aborts the crawl.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from .core import normalize
from .core.change_tracking import content_hash
from .core.exporters import JsonLinesExporter
from .core.normalize import normalize_category_from_description
from .core.schema import missing_required, ordered
from .core.scope import classify_record

logger = logging.getLogger(__name__)


def _as_dict(item) -> Dict[str, Any]:
    return ItemAdapter(item).asdict() if not isinstance(item, dict) else item


class _CrawlerAware:
    """Mixin that saves the crawler so pipelines can reach stats and settings
    without relying on the deprecated spider argument."""

    crawler = None

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls()
        obj.crawler = crawler
        return obj

    def _stats(self):
        return getattr(self.crawler, "stats", None) if self.crawler else None


class CleaningPipeline:
    """Trim strings, clean list fields, preserve variants, fill brand_normalized."""

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        for key in ("title", "description", "vendor", "brand", "subcategory"):
            if isinstance(record.get(key), str):
                record[key] = record[key].strip()
        for key in ("image_urls", "sizes", "material"):
            record[key] = normalize.clean_list(record.get(key))
        record["colors"] = normalize.normalize_colors(record.get("colors"))
        if not record.get("main_image") and record.get("image_urls"):
            record["main_image"] = record["image_urls"][0]
        if not isinstance(record.get("attributes"), dict):
            record["attributes"] = {}
        if not isinstance(record.get("variants"), list):
            record["variants"] = []
        if not record.get("brand_normalized") and record.get("brand"):
            record["brand_normalized"] = record["brand"].lower()
        return record


class PriceNormalizationPipeline:
    """Ensure product and variant prices are Decimal and currency is a code."""

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        record["price"] = normalize.to_decimal(record.get("price"))
        record["original_price"] = normalize.to_decimal(record.get("original_price"))
        record["currency"] = normalize.normalize_currency(record.get("currency"))
        if (
            record["price"] is not None
            and record["original_price"] is not None
            and record["original_price"] <= record["price"]
        ):
            record["original_price"] = None

        for variant in record.get("variants", []):
            variant["price"] = normalize.to_decimal(variant.get("price"))
            variant["original_price"] = normalize.to_decimal(variant.get("original_price"))
            variant["currency"] = normalize.normalize_currency(variant.get("currency"))
            if (
                variant["price"] is not None
                and variant["original_price"] is not None
                and variant["original_price"] <= variant["price"]
            ):
                variant["original_price"] = None
        return record


class CategoryNormalizationPipeline:
    """Backfill category, gender and colours for spiders that left them blank.

    Two-pass strategy for category:
    1. Primary: structured fields (subcategory, title, tags). Covers most stores.
    2. Description fallback: for stores like lablanca that use single model
       names as titles ("Vivienne", "Ophelia") with all garment information in
       the description. The description is tried last because it is marketing
       copy and slightly more likely to produce a wrong category.
    """

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        attrs = record.get("attributes", {})
        tags = attrs.get("tags", []) if isinstance(attrs, dict) else []
        hints = [record.get("subcategory"), record.get("title"), " ".join(tags)]
        if not record.get("category"):
            record["category"] = normalize.normalize_category(*hints)
        if not record.get("category") and record.get("description"):
            record["category"] = normalize_category_from_description(record["description"])
        if not record.get("gender"):
            record["gender"] = normalize.normalize_gender(*hints)
        record["colors"] = normalize.normalize_colors(record.get("colors"))
        return record


class ScopeFilterPipeline(_CrawlerAware):
    """Accept clothing and footwear; reject everything else with a reason code.

    This is the single authoritative scope gate for the entire system. It runs
    after category normalisation (so the normalised category is available) but
    before validation, change tracking, dedup, and export, meaning rejected
    items never reach JSON files, PostgreSQL, pgvector, or the CLIP pipeline.

    Spiders no longer need their own fashion filters; all scope decisions happen
    here so rejection counts are always accurate and reported.
    """

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        self._stats_inc("egyscraper/scope/seen")
        scope = classify_record(record)
        if scope["is_supported"]:
            record["scope"] = scope
            return record
        reason = scope.get("rejection_reason", "out_of_scope")
        self._stats_inc(f"egyscraper/rejected/{reason}")
        raise DropItem(f"out of scope ({reason}): {record.get('title', '')[:80]}")

    def _stats_inc(self, key: str) -> None:
        crawler = getattr(self, "crawler", None)
        if crawler is not None and getattr(crawler, "stats", None) is not None:
            self.crawler.stats.inc_value(key)


class ValidationPipeline(_CrawlerAware):
    """Reject any record missing a required field (title, price, images, url).

    image_urls is skipped when the spider sets ``images_required = False``.
    New Balance is the known case: its product pages render images via JS so
    JSON-LD always carries image:[] from the server response.  Those products
    are exported without images so downstream processing (Playwright backfill,
    CLIP embedding) can handle them rather than losing them entirely.
    """

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        missing = missing_required(record)
        if missing:
            # Allow stores with JS-rendered images to export without image_urls
            images_required = getattr(spider, "images_required", True)
            if not images_required and missing == ["image_urls"]:
                # Log a warning but do not drop the item
                stats = self._stats()
                if stats:
                    stats.inc_value("egyscraper/missing_images_allowed")
                return record
            stats = self._stats()
            if stats:
                stats.inc_value("egyscraper/dropped_missing_fields")
            raise DropItem(f"missing required fields {missing}: {record.get('product_url')}")
        return record


class ChangeTrackingPipeline:
    """Stamp the content hash and the first and last seen timestamps.

    content_hash lets a future incremental crawl tell whether a product really
    changed. first_seen is set here and preserved across crawls at the database
    layer via COALESCE on upsert.
    """

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        record["content_hash"] = content_hash(record)
        stamp = record.get("scraped_at")
        record["last_seen"] = stamp
        if not record.get("first_seen"):
            record["first_seen"] = stamp
        return record


class DeduplicationPipeline(_CrawlerAware):
    """Drop records whose deterministic product_id was already emitted."""

    def __init__(self):
        self._seen = set()

    @classmethod
    def from_crawler(cls, crawler):
        obj = cls()
        obj.crawler = crawler
        return obj

    def process_item(self, item, spider=None):
        record = _as_dict(item)
        pid = record.get("product_id")
        if not pid:
            raise DropItem("record has no product_id")
        if pid in self._seen:
            stats = self._stats()
            if stats:
                stats.inc_value("egyscraper/dropped_duplicates")
            raise DropItem(f"duplicate product_id {pid}")
        self._seen.add(pid)
        return record


class ExportPipeline(_CrawlerAware):
    """Stream accepted records to JSONL and optionally a JSON array."""

    exporter: Optional[JsonLinesExporter] = None

    def _spider(self):
        return getattr(self.crawler, "spider", None) if self.crawler else None

    def open_spider(self, spider=None):
        spider = spider or self._spider()
        settings = self.crawler.settings
        out_dir = settings.get("OUTPUT_DIR", "Products")
        slug = getattr(spider, "store_slug", None) or getattr(spider, "name", "spider")
        self._slug = slug
        build_array = settings.getbool("EXPORT_JSON_ARRAY", True)
        self.exporter = JsonLinesExporter(
            jsonl_path=f"{out_dir}/{slug}_products.jsonl",
            json_array_path=f"{out_dir}/{slug}_products.json" if build_array else None,
            flush_every=settings.getint("EXPORT_FLUSH_EVERY", 200),
        )
        self.exporter.open()
        logger.info("Exporting to %s/%s_products.json", out_dir, slug)

    def process_item(self, item, spider=None):
        self.exporter.write(ordered(_as_dict(item)))
        return item

    def close_spider(self, spider=None):
        if self.exporter is None:
            return
        try:
            self.exporter.close()
            final = self.exporter.json_array_path or self.exporter.jsonl_path
            logger.info("Exported %d records to %s", self.exporter.count, final)
            # Remove intermediate JSONL once the JSON array has been built.
            if self.exporter.json_array_path:
                try:
                    os.remove(self.exporter.jsonl_path)
                except OSError:
                    pass
        except OSError as exc:
            # The data is intact in the .tmp file; surface a clear, actionable
            # message at WARNING so it is visible at the default log level.
            logger.warning(
                "EXPORT RENAME FAILED for %s — data is safe in %s\n"
                "Cause: %s\n"
                "To recover: rename the .tmp file manually, or re-run the spider "
                "(it will overwrite .tmp and retry the rename).",
                self.exporter.jsonl_path,
                self.exporter._tmp_path,
                exc,
            )
