import cloudscraper
from scrapy.http import HtmlResponse
from scrapy.exceptions import IgnoreRequest
from twisted.internet.threads import deferToThread
import logging

class CloudScraperMiddleware:
    def __init__(self):
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        self.logger = logging.getLogger("cloudscraper")

    async def process_request(self, request):
        # We can bypass standard processing for specific domains
        domains_to_bypass = ['jumia.com.eg', 'lcwaikiki.eg', 'defacto.com.eg']
        if not any(d in request.url for d in domains_to_bypass):
            return None # Use normal scrapy downloader

        # deferToThread runs the blocking cloudscraper call in a thread pool
        return await deferToThread(self._fetch, request)

    def _fetch(self, request):
        try:
            resp = self.scraper.get(request.url, timeout=20)
            
            if resp.status_code in [403, 429]:
                self.logger.warning(f"Cloudscraper got {resp.status_code} for {request.url}")
            
            return HtmlResponse(
                url=request.url,
                body=resp.content,
                encoding='utf-8',
                request=request,
                status=resp.status_code
            )
        except Exception as e:
            self.logger.error(f"Cloudscraper error on {request.url}: {e}")
            raise IgnoreRequest()
