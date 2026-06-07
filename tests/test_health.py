"""Tests for crawl health reporting and the yield aggregation CLI."""

import json

from egyscraper.core.health import build_report, format_report
from egyscraper.report import collect, render


def test_build_report_basic():
    stats = {
        "item_scraped_count": 100,
        "downloader/request_count": 25,
        "retry/count": 3,
        "downloader/exception_count": 1,
        "egyscraper/request_errors": 2,
        "egyscraper/dropped_duplicates": 5,
        "elapsed_time_seconds": 12.5,
        "finish_reason": "finished",
    }
    r = build_report(stats, "townteam")
    assert r["store"] == "townteam"
    assert r["products_scraped"] == 100
    assert r["requests_made"] == 25
    assert r["retries"] == 3
    assert r["failures"] == 3          # 1 exception + 2 request errors
    assert r["dropped_items"] == 5
    assert r["duration_seconds"] == 12.5
    assert r["products_per_request"] == 4.0


def test_build_report_tolerates_missing_keys():
    r = build_report({}, "empty")
    assert r["products_scraped"] == 0
    assert r["requests_made"] == 0
    assert r["products_per_request"] == 0.0


def test_format_report_is_readable():
    r = build_report({"item_scraped_count": 5, "downloader/request_count": 5}, "s")
    text = format_report(r)
    assert "products" in text and "s" in text


def test_collect_and_render(tmp_path):
    # Two stores with output, sorted by yield in the table.
    for slug, n in (("big", 3), ("small", 1)):
        d = tmp_path / slug
        d.mkdir()
        (d / "products.jsonl").write_text(
            "\n".join(json.dumps({"product_id": str(i)}) for i in range(n)) + "\n",
            encoding="utf-8",
        )
    (tmp_path / "big" / "crawl_report.json").write_text(
        json.dumps({"requests_made": 2, "failures": 0, "duration_seconds": 1.2}),
        encoding="utf-8",
    )
    rows = collect(str(tmp_path))
    assert [r["store"] for r in rows] == ["big", "small"]  # sorted desc
    assert rows[0]["products"] == 3
    assert rows[0]["requests"] == 2

    table = render(rows)
    assert "TOTAL" in table
    assert "4" in table  # 3 + 1


def test_collect_empty_dir(tmp_path):
    assert collect(str(tmp_path)) == []
    assert render([]) == "no store output found"
