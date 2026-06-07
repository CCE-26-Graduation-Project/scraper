"""Downloader middlewares.

UserAgentRotationMiddleware rotates a full, coherent browser profile per
request (user agent plus matching client hint headers), which is harder for a
naive WAF to flag than a lone user agent string. ProxyMiddleware is a
documented hook, disabled until a proxy is configured.

These help against simple bot rules. They do not defeat an aggressive bot
manager (Akamai, DataDome, Cloudflare bot mode), which keys on the source IP
and a real browser fingerprint; those need a residential proxy or Playwright.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, List

logger = logging.getLogger(__name__)

# Coherent profiles: a Chrome user agent ships matching sec-ch-ua client hints;
# a Firefox user agent ships none (Firefox does not send them). Keeping them
# consistent avoids the mismatch that flags a request as automated.
_PROFILES: List[Dict[str, str]] = [
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="124", "Google Chrome";v="124", "Not.A/Brand";v="99"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"Windows"',
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "sec_ch_ua": '"Chromium";v="123", "Google Chrome";v="123", "Not.A/Brand";v="99"',
        "sec_ch_ua_mobile": "?0",
        "sec_ch_ua_platform": '"macOS"',
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
              "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        # Safari sends no sec-ch-ua hints.
    },
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        # Firefox sends no sec-ch-ua hints.
    },
]


class UserAgentRotationMiddleware:
    """Assign a coherent browser profile to each outgoing request.

    A request that already carries a User-Agent is left alone, so spider level
    overrides win. Profiles are read from the BROWSER_PROFILES setting when
    provided, otherwise a built in set is used.
    """

    def __init__(self, profiles: List[Dict[str, str]]):
        self.profiles = profiles or _PROFILES

    @classmethod
    def from_crawler(cls, crawler):
        profiles = crawler.settings.get("BROWSER_PROFILES") or _PROFILES
        return cls(profiles)

    def process_request(self, request, spider=None):
        if b"User-Agent" in request.headers:
            return None
        profile = random.choice(self.profiles)
        request.headers[b"User-Agent"] = profile["ua"]
        if profile.get("sec_ch_ua"):
            request.headers.setdefault(b"sec-ch-ua", profile["sec_ch_ua"])
            request.headers.setdefault(b"sec-ch-ua-mobile", profile.get("sec_ch_ua_mobile", "?0"))
            request.headers.setdefault(b"sec-ch-ua-platform", profile.get("sec_ch_ua_platform", '"Windows"'))
        return None


class ProxyMiddleware:
    """Route requests through a proxy when PROXY_URL or PROXY_LIST is set.

    Disabled by default. To use a residential or rotating pool, set PROXY_LIST
    in settings or the PROXY_URL environment variable. This is the single place
    to integrate a provider, and the recommended next step for stores that 403.
    """

    def __init__(self, proxy_list: List[str], single_proxy: str):
        self.proxy_list = proxy_list
        self.single_proxy = single_proxy

    @classmethod
    def from_crawler(cls, crawler):
        import os
        return cls(crawler.settings.getlist("PROXY_LIST"), os.getenv("PROXY_URL", ""))

    def process_request(self, request, spider=None):
        if "proxy" in request.meta:
            return None
        if self.proxy_list:
            request.meta["proxy"] = random.choice(self.proxy_list)
        elif self.single_proxy:
            request.meta["proxy"] = self.single_proxy
        return None
