"""Helpers for API based extraction (REST, mobile and GraphQL endpoints).

These build properly formed Scrapy requests for structured endpoints, which
sit above HTML scraping in the extraction priority order. Keeping the request
construction here avoids each spider re implementing JSON body encoding,
header handling and response parsing.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

import scrapy


DEFAULT_JSON_HEADERS: Dict[str, str] = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def json_request(
    url: str,
    callback: Callable,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> scrapy.Request:
    """Build a Scrapy request for a JSON REST or mobile API endpoint."""
    merged_headers = dict(DEFAULT_JSON_HEADERS)
    if headers:
        merged_headers.update(headers)
    body = json.dumps(payload) if payload is not None else None
    return scrapy.Request(
        url=url,
        method=method,
        headers=merged_headers,
        body=body,
        callback=callback,
        meta=meta or {},
        **kwargs,
    )


def graphql_request(
    url: str,
    query: str,
    callback: Callable,
    variables: Optional[Dict[str, Any]] = None,
    operation_name: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    meta: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> scrapy.Request:
    """Build a POST Scrapy request for a GraphQL endpoint.

    Pass the query string and a variables dict; pagination is handled by the
    caller by issuing follow up requests with updated variables.
    """
    payload: Dict[str, Any] = {"query": query, "variables": variables or {}}
    if operation_name:
        payload["operationName"] = operation_name
    return json_request(
        url=url,
        callback=callback,
        method="POST",
        payload=payload,
        headers=headers,
        meta=meta,
        **kwargs,
    )


def parse_json(response) -> Any:
    """Parse a Scrapy response body as JSON, returning None on failure.

    Returning None instead of raising lets a spider log and continue past a
    single bad response rather than aborting the whole crawl.
    """
    try:
        return json.loads(response.text)
    except (ValueError, AttributeError):
        return None
