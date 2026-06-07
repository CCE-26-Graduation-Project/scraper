"""Tests for the REST, mobile and GraphQL request helpers."""

import json

from egyscraper.core import api


def _noop(_response):
    return None


def test_json_request_get_has_no_body():
    req = api.json_request("https://x/api", _noop)
    assert req.method == "GET"
    assert req.body == b""
    assert req.headers.get(b"Accept") == b"application/json"


def test_json_request_post_encodes_payload():
    req = api.json_request("https://x/api", _noop, method="POST", payload={"a": 1})
    assert req.method == "POST"
    assert json.loads(req.body) == {"a": 1}
    assert req.headers.get(b"Content-Type") == b"application/json"


def test_json_request_merges_custom_headers():
    req = api.json_request("https://x/api", _noop, headers={"X-Token": "abc"})
    assert req.headers.get(b"X-Token") == b"abc"
    assert req.headers.get(b"Accept") == b"application/json"


def test_graphql_request_builds_body():
    req = api.graphql_request(
        "https://x/graphql",
        "query Q($p:Int){items(page:$p){id}}",
        _noop,
        variables={"p": 2},
        operation_name="Q",
    )
    body = json.loads(req.body)
    assert body["variables"] == {"p": 2}
    assert body["operationName"] == "Q"
    assert "query" in body


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def test_parse_json_valid():
    assert api.parse_json(_FakeResponse('{"k": 1}')) == {"k": 1}


def test_parse_json_invalid_returns_none():
    assert api.parse_json(_FakeResponse("not json")) is None
