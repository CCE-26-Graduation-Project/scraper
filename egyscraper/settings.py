"""Scrapy settings for the unified egyscraper project.

Tuned for a polite, fault tolerant, asynchronous crawl across many stores.
Values that an operator might reasonably change at run time can be overridden
from the environment without editing this file.
"""

import os

BOT_NAME = "egyscraper"

SPIDER_MODULES = ["egyscraper.spiders"]
NEWSPIDER_MODULE = "egyscraper.spiders"

# ---------------------------------------------------------------------------
# Politeness and concurrency
# ---------------------------------------------------------------------------
# Obey robots.txt by default. Structured public endpoints such as Shopify's
# products.json are generally permitted; override per spider only with reason.
ROBOTSTXT_OBEY = os.getenv("ROBOTSTXT_OBEY", "true").lower() == "true"

CONCURRENT_REQUESTS = int(os.getenv("CONCURRENT_REQUESTS", "16"))
CONCURRENT_REQUESTS_PER_DOMAIN = int(os.getenv("CONCURRENT_REQUESTS_PER_DOMAIN", "4"))
DOWNLOAD_DELAY = float(os.getenv("DOWNLOAD_DELAY", "0.5"))
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "30"))

# AutoThrottle adapts the delay to server latency so the crawler backs off
# under load instead of hammering a struggling store.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 15.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

# ---------------------------------------------------------------------------
# Retry: recover from transient failures without losing the whole crawl
# ---------------------------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = int(os.getenv("RETRY_TIMES", "3"))
# 403 is included because each retry is sent with a freshly rotated browser
# profile (see middlewares), so a fingerprint based block can sometimes be
# cleared on retry. It does not help IP based blocks, which need a proxy.
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504, 522, 524, 408]

# ---------------------------------------------------------------------------
# HTTP cache: speed up development and re runs, and avoid refetching pages
# ---------------------------------------------------------------------------
HTTPCACHE_ENABLED = os.getenv("HTTPCACHE_ENABLED", "false").lower() == "true"
HTTPCACHE_EXPIRATION_SECS = int(os.getenv("HTTPCACHE_EXPIRATION_SECS", "86400"))
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [429, 500, 502, 503, 504]
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# ---------------------------------------------------------------------------
# Middlewares: user agent rotation on, proxy hook present but inert
# ---------------------------------------------------------------------------
DOWNLOADER_MIDDLEWARES = {
    # Disable the built in single user agent middleware in favour of rotation.
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,
    "egyscraper.middlewares.UserAgentRotationMiddleware": 400,
    "egyscraper.middlewares.ProxyMiddleware": 410,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Browser like default headers. A bare scraper sends almost no headers, which
# trips simple WAF rules; a full, realistic header set gets past many of them.
# It is not enough on its own for aggressive bot managers (those need a
# residential proxy or Playwright; see below), but it is the cheapest first
# step and helps with stores that 403 a plain request. User-Agent is left to
# the rotation middleware. Accept-Encoding is left to the compression
# middleware. Arabic is included since these are Egyptian storefronts.
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Proxy and CAPTCHA placeholders (inactive). See middlewares.ProxyMiddleware.
# Anti bot escalation, in order of effort, for stores that 403 or challenge:
#   1. The default headers above (already on).
#   2. A residential proxy pool: set PROXY_LIST or the PROXY_URL env var.
#   3. Playwright with a real browser fingerprint (see the handlers below).
# PROXY_LIST = ["http://user:pass@proxy-host:port"]
# CAPTCHA_PROVIDER = "..."   # integrate a solver here when a provider is chosen

# ---------------------------------------------------------------------------
# Item pipelines (lower number runs first)
# ---------------------------------------------------------------------------
ITEM_PIPELINES = {
    "egyscraper.pipelines.CleaningPipeline": 200,
    "egyscraper.pipelines.PriceNormalizationPipeline": 300,
    "egyscraper.pipelines.CategoryNormalizationPipeline": 400,
    # Deduplication runs BEFORE scope so scope stats count unique products only.
    # When a store is crawled via many collections the same product appears many
    # times; letting duplicates through to scope would inflate the scope counts.
    "egyscraper.pipelines.DeduplicationPipeline": 450,
    "egyscraper.pipelines.ScopeFilterPipeline": 460,
    "egyscraper.pipelines.ValidationPipeline": 470,
    "egyscraper.pipelines.ChangeTrackingPipeline": 480,
    "egyscraper.pipelines.ExportPipeline": 900,
}

# Where ExportPipeline writes per store output.
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "Products")

# Export tuning. The JSONL stream is canonical; the JSON array is convenient for
# small catalogs but can be turned off for very large ones. Flushing is batched
# so write throughput stays high without losing more than one batch on a crash.
EXPORT_JSON_ARRAY = os.getenv("EXPORT_JSON_ARRAY", "true").lower() == "true"
EXPORT_FLUSH_EVERY = int(os.getenv("EXPORT_FLUSH_EVERY", "200"))

# Crawl health report written per store on spider close (Task 6 tooling).
EXTENSIONS = {
    "egyscraper.core.health.CrawlHealthExtension": 500,
}

# ---------------------------------------------------------------------------
# Browser automation (Playwright): present but used only as a last resort
# ---------------------------------------------------------------------------
# Install scrapy-playwright and uncomment to enable for spiders that genuinely
# need a rendered DOM. Most target stores expose a structured endpoint and
# should never reach for this.
#
# DOWNLOAD_HANDLERS = {
#     "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
#     "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
# }
# TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# PLAYWRIGHT_BROWSER_TYPE = "chromium"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
LOG_DATEFORMAT = "%Y-%m-%d %H:%M:%S"

# Modern defaults
FEED_EXPORT_ENCODING = "utf-8"
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
