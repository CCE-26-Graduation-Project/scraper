"""Tests for the browser profile rotation middleware."""

from scrapy import Request

from egyscraper.middlewares import UserAgentRotationMiddleware, _PROFILES


def test_sets_user_agent():
    mw = UserAgentRotationMiddleware(_PROFILES)
    req = Request("https://x/")
    mw.process_request(req)
    assert req.headers.get(b"User-Agent") is not None


def test_does_not_override_existing_user_agent():
    mw = UserAgentRotationMiddleware(_PROFILES)
    req = Request("https://x/", headers={"User-Agent": "custom"})
    mw.process_request(req)
    assert req.headers.get(b"User-Agent") == b"custom"


def test_chrome_profile_sends_matching_client_hints():
    # Force a Chrome profile (one that carries sec-ch-ua).
    chrome = [p for p in _PROFILES if p.get("sec_ch_ua")][0]
    mw = UserAgentRotationMiddleware([chrome])
    req = Request("https://x/")
    mw.process_request(req)
    assert req.headers.get(b"sec-ch-ua") is not None
    assert req.headers.get(b"sec-ch-ua-platform") is not None


def test_safari_profile_sends_no_client_hints():
    safari = [p for p in _PROFILES if not p.get("sec_ch_ua")][0]
    mw = UserAgentRotationMiddleware([safari])
    req = Request("https://x/")
    mw.process_request(req)
    assert req.headers.get(b"sec-ch-ua") is None
