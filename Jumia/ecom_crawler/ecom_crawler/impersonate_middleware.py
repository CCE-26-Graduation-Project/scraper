from curl_cffi import requests as cffi_requests
from scrapy.http import HtmlResponse
from scrapy.exceptions import IgnoreRequest
import asyncio
import logging

class ImpersonateMiddleware:
    def __init__(self):
        self.logger = logging.getLogger("impersonate_middleware")

    async def process_request(self, request, spider=None):
        domains_to_bypass = ['jumia.com.eg', 'lcwaikiki.eg', 'defacto.com.eg']
        # removed emma and sigmafit to let them naturally fail/dns in normal or just bypass
        if not any(d in request.url for d in domains_to_bypass):
            return None # Use normal scrapy downloader

        # Run blocking curl_cffi in asyncio thread
        return await asyncio.to_thread(self._fetch, request)

    def _fetch(self, request):
        try:
            # We must map Scrapy request parameters (headers, method, etc.)
            headers = {k.decode(): v[0].decode() for k, v in request.headers.items()}
            # Impersonate chrome124 to bypass Akamai and Cloudflare
            resp = cffi_requests.get(
                request.url,
                headers=headers,
                impersonate="chrome124",
                timeout=25,
                allow_redirects=True
            )

            if resp.status_code in [403, 429]:
                self.logger.warning(f"Impersonate got {resp.status_code} for {request.url}")
            
            return HtmlResponse(
                url=resp.url, # handle redirects
                body=resp.content,
                encoding='utf-8',
                request=request,
                status=resp.status_code
            )
        except Exception as e:
            self.logger.error(f"Impersonate error on {request.url}: {e}")
            raise IgnoreRequest()
