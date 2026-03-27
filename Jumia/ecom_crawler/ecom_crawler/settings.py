BOT_NAME = "ecom_crawler"

SPIDER_MODULES = ["ecom_crawler.spiders"]
NEWSPIDER_MODULE = "ecom_crawler.spiders"

# Strong default identity. You can rotate from middleware later if needed.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

ROBOTSTXT_OBEY = False

# Performance + politeness balance.
CONCURRENT_REQUESTS = 24
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_DELAY = 0.5
RANDOMIZE_DOWNLOAD_DELAY = True

DOWNLOAD_TIMEOUT = 25

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.8
AUTOTHROTTLE_MAX_DELAY = 8.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 4.0
AUTOTHROTTLE_DEBUG = False

RETRY_ENABLED = True
RETRY_TIMES = 4
RETRY_HTTP_CODES = [403, 408, 429, 500, 502, 503, 504, 522, 524]

# Defensive default stops so no site can crawl indefinitely.
CLOSESPIDER_TIMEOUT = 300
CLOSESPIDER_PAGECOUNT = 800

COOKIES_ENABLED = True
TELNETCONSOLE_ENABLED = False

LOG_LEVEL = "INFO"

ITEM_PIPELINES = {
    "ecom_crawler.pipelines.DedupValidationPipeline": 300,
}

DOWNLOADER_MIDDLEWARES = {
    "ecom_crawler.impersonate_middleware.ImpersonateMiddleware": 100,
}

FEED_EXPORT_ENCODING = "utf-8"

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_INDENT = 2

# Scrapy-Playwright integration (enable only for JS-heavy targets):
# DOWNLOAD_HANDLERS = {
#     "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
#     "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
# }
# DOWNLOADER_MIDDLEWARES = {
#     "scrapy_playwright.middleware.ScrapyPlaywrightDownloaderMiddleware": 543,
# }
# TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
# PLAYWRIGHT_BROWSER_TYPE = "chromium"
# PLAYWRIGHT_LAUNCH_OPTIONS = {"headless": True}
# PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30 * 1000
