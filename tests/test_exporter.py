"""Tests for the hardened JsonLinesExporter."""

import json
import os
from decimal import Decimal

import simplejson

from egyscraper.core.exporters import JsonLinesExporter, dumps


def test_decimal_serialized_as_number():
    out = dumps({"price": Decimal("799.00")})
    assert out == '{"price": 799.00}'
    # round trips back to an exact Decimal, never a float
    assert simplejson.loads(out, use_decimal=True)["price"] == Decimal("799.00")


def test_writes_jsonl_and_counts(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    exp = JsonLinesExporter(str(jsonl))
    exp.open()
    exp.write({"product_id": "a", "price": Decimal("10.00")})
    exp.write({"product_id": "b", "price": Decimal("20.50")})
    exp.close()
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert exp.count == 2
    assert simplejson.loads(lines[1], use_decimal=True)["price"] == Decimal("20.50")


def test_variants_preserved_in_output(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    exp = JsonLinesExporter(str(jsonl))
    exp.open()
    record = {
        "product_id": "a",
        "price": Decimal("799.00"),
        "variants": [
            {"sku": "X-S", "size": "S", "price": Decimal("799.00"), "available": True},
            {"sku": "X-M", "size": "M", "price": Decimal("849.00"), "available": False},
        ],
    }
    exp.write(record)
    exp.close()
    loaded = simplejson.loads(jsonl.read_text(encoding="utf-8").strip(), use_decimal=True)
    assert len(loaded["variants"]) == 2
    assert loaded["variants"][1]["price"] == Decimal("849.00")
    assert loaded["variants"][1]["available"] is False


def test_builds_valid_json_array(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    arr = tmp_path / "products.json"
    exp = JsonLinesExporter(str(jsonl), str(arr))
    exp.open()
    records = [{"product_id": str(i), "price": Decimal("1.00")} for i in range(3)]
    for r in records:
        exp.write(r)
    exp.close()
    loaded = simplejson.loads(arr.read_text(encoding="utf-8"), use_decimal=True)
    assert loaded == records


def test_json_array_opt_out(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    arr = tmp_path / "products.json"
    exp = JsonLinesExporter(str(jsonl), json_array_path=None)
    exp.open()
    exp.write({"product_id": "a"})
    exp.close()
    assert jsonl.exists()
    assert not arr.exists()


def test_flush_batching_writes_all(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    exp = JsonLinesExporter(str(jsonl), flush_every=10)
    exp.open()
    for i in range(25):  # more than two flush batches
        exp.write({"product_id": str(i)})
    exp.close()
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 25


def test_unicode_preserved(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    exp = JsonLinesExporter(str(jsonl))
    exp.open()
    exp.write({"title": "قميص قطن"})
    exp.close()
    assert "قميص" in jsonl.read_text(encoding="utf-8")


def test_empty_run_preserves_previous_data(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    # First run produces good data.
    exp = JsonLinesExporter(str(jsonl))
    exp.open()
    exp.write({"product_id": "a"})
    exp.write({"product_id": "b"})
    exp.close()
    assert len(jsonl.read_text(encoding="utf-8").strip().splitlines()) == 2

    # Second run is blocked and produces nothing; previous data must survive.
    exp2 = JsonLinesExporter(str(jsonl))
    exp2.open()
    exp2.close()  # zero writes
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # not clobbered
    assert not (tmp_path / "products.jsonl.tmp").exists()


def test_empty_first_run_writes_empty(tmp_path):
    jsonl = tmp_path / "products.jsonl"
    exp = JsonLinesExporter(str(jsonl))
    exp.open()
    exp.close()  # zero writes, no previous file
    assert jsonl.exists()  # an empty first run still produces the file


# ── Rename robustness tests (added after Windows .tmp bug) ───────────────────
import time as _time


def _locked_replace(fail_times):
    """Return an os.replace replacement that fails the first N calls."""
    real = os.replace
    calls = [0]
    def patched(src, dst):
        calls[0] += 1
        if calls[0] <= fail_times:
            raise PermissionError(f"[WinError 32] locked (call {calls[0]})")
        return real(src, dst)
    return patched


def test_rename_retries_on_transient_lock(tmp_path, monkeypatch):
    path = str(tmp_path / "products.jsonl")
    exp = JsonLinesExporter(path)
    exp.open()
    exp.write({"title": "T-Shirt", "price": 100})

    # First 2 attempts fail, 3rd succeeds
    monkeypatch.setattr(os, "replace", _locked_replace(2))
    monkeypatch.setattr(_time, "sleep", lambda _: None)   # skip actual sleeps
    exp.close()

    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    assert "T-Shirt" in open(path).read()


def test_rename_fallback_on_persistent_lock(tmp_path, monkeypatch):
    path = str(tmp_path / "products.jsonl")
    (tmp_path / "products.jsonl").write_text("old\n")
    exp = JsonLinesExporter(path)
    exp.open()
    exp.write({"title": "Hoodie", "price": 200})

    # All os.replace calls fail → must succeed via delete+rename fallback
    monkeypatch.setattr(os, "replace", _locked_replace(999))
    monkeypatch.setattr(_time, "sleep", lambda _: None)
    exp.close()

    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
    assert "Hoodie" in open(path).read()


def test_no_tmp_left_on_normal_close(tmp_path):
    path = str(tmp_path / "products.jsonl")
    exp = JsonLinesExporter(path)
    exp.open()
    exp.write({"title": "Jeans", "price": 300})
    exp.close()
    assert os.path.exists(path)
    assert not os.path.exists(path + ".tmp")
