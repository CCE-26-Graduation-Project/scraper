"""Crawl health reporting.

Turns Scrapy's end of crawl statistics into a compact health report for every
spider run: products scraped, requests made, retries, failures, duration, and
average products per request. ``build_report`` is a pure function (easy to
test); ``CrawlHealthExtension`` wires it into Scrapy and writes the report next
to the store's output.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def build_report(stats: Dict[str, Any], slug: str) -> Dict[str, Any]:
    """Build a health report dict from a Scrapy stats mapping.

    Tolerant of missing keys (a crawl that died early still reports cleanly).
    Includes scope classification breakdown: total discovered by the scope
    layer, accepted (clothing + footwear), rejected with per reason counts.
    """
    items = int(stats.get("item_scraped_count", 0) or 0)
    requests = int(stats.get("downloader/request_count", 0) or 0)
    retries = int(stats.get("retry/count", 0) or 0)
    failures = (
        int(stats.get("downloader/exception_count", 0) or 0)
        + int(stats.get("egyscraper/request_errors", 0) or 0)
    )
    dropped = (
        int(stats.get("egyscraper/dropped_missing_fields", 0) or 0)
        + int(stats.get("egyscraper/dropped_duplicates", 0) or 0)
    )

    duration = stats.get("elapsed_time_seconds")
    if duration is None:
        start = stats.get("start_time")
        finish = stats.get("finish_time") or datetime.now(timezone.utc)
        if isinstance(start, datetime):
            duration = (finish - start).total_seconds()
    duration = round(float(duration), 2) if duration is not None else None

    per_request = round(items / requests, 3) if requests else 0.0

    # Scope breakdown ─────────────────────────────────────────────────────────
    scope_seen = int(stats.get("egyscraper/scope/seen", 0) or 0)
    rejection_breakdown: Dict[str, int] = {}
    total_rejected = 0
    for key, value in stats.items():
        if key.startswith("egyscraper/rejected/"):
            reason = key[len("egyscraper/rejected/"):]
            count = int(value or 0)
            rejection_breakdown[reason] = count
            total_rejected += count
    scope_accepted = scope_seen - total_rejected

    return {
        "store": slug,
        "products_scraped": items,
        "requests_made": requests,
        "retries": retries,
        "failures": failures,
        "dropped_items": dropped,
        "duration_seconds": duration,
        "products_per_request": per_request,
        "finish_reason": stats.get("finish_reason"),
        # Scope section – zero-filled so the key is always present
        "scope_total_discovered": scope_seen,
        "scope_accepted": scope_accepted,
        "scope_rejected": total_rejected,
        "scope_rejection_breakdown": rejection_breakdown,
    }


def format_report(report: Dict[str, Any]) -> str:
    breakdown = report.get("scope_rejection_breakdown") or {}
    breakdown_str = (
        "  " + ", ".join(f"{r}: {n}" for r, n in sorted(breakdown.items()))
        if breakdown else ""
    )
    lines = [
        f"crawl health [{report['store']}]: "
        f"{report['products_scraped']} products, "
        f"{report['requests_made']} requests, "
        f"{report['retries']} retries, "
        f"{report['failures']} failures, "
        f"{report['duration_seconds']}s, "
        f"{report['products_per_request']} products/request",
        f"  scope: {report.get('scope_total_discovered',0)} seen, "
        f"{report.get('scope_accepted',0)} accepted, "
        f"{report.get('scope_rejected',0)} rejected",
    ]
    if breakdown_str:
        lines.append(f"  rejection breakdown:{breakdown_str}")
    return "\n".join(lines)


class CrawlHealthExtension:
    """Write a crawl_report.json and log a health summary when a spider closes.

    Enable via the EXTENSIONS setting (already wired in settings.py).
    """

    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    @classmethod
    def from_crawler(cls, crawler):
        from scrapy import signals
        ext = cls(crawler.settings.get("OUTPUT_DIR", "data"))
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        return ext

    def spider_closed(self, spider):
        try:
            stats = spider.crawler.stats.get_stats()
            slug = getattr(spider, "store_slug", None) or spider.name
            report = build_report(stats, slug)
            spider.logger.info(format_report(report))
            path = os.path.join(self.output_dir, slug, "crawl_report.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
        except Exception as exc:  # never let reporting break a finished crawl
            logger.warning("could not write crawl report: %s", exc)
