"""Tests for the incremental crawl foundation."""

from decimal import Decimal

from egyscraper.core.change_tracking import (
    CrawlState,
    content_hash,
    detect_changes,
)
from egyscraper.core.schema import empty_product


def _rec(pid, price="100.00", title="Tee", available=True):
    r = empty_product()
    r.update(
        {
            "product_id": pid,
            "title": title,
            "price": Decimal(price),
            "availability": "in_stock" if available else "out_of_stock",
            "variants": [{"sku": f"{pid}-1", "price": Decimal(price), "available": available}],
            "scraped_at": "2026-06-01T00:00:00+00:00",
        }
    )
    return r


# -- content hash ---------------------------------------------------------
def test_hash_stable_for_same_content():
    assert content_hash(_rec("a")) == content_hash(_rec("a"))


def test_hash_changes_on_price():
    assert content_hash(_rec("a", price="100.00")) != content_hash(_rec("a", price="90.00"))


def test_hash_changes_on_availability():
    assert content_hash(_rec("a", available=True)) != content_hash(_rec("a", available=False))


def test_hash_changes_on_title():
    assert content_hash(_rec("a", title="Tee")) != content_hash(_rec("a", title="Hoodie"))


def test_hash_ignores_volatile_fields():
    a = _rec("a")
    b = _rec("a")
    b["scraped_at"] = "2030-01-01T00:00:00+00:00"  # volatile, not part of content
    b["last_seen"] = "2030-01-01T00:00:00+00:00"
    assert content_hash(a) == content_hash(b)


# -- change detection -----------------------------------------------------
def test_detect_new_updated_unchanged_removed():
    previous = {
        "keep": content_hash(_rec("keep")),
        "change": content_hash(_rec("change", price="100.00")),
        "gone": content_hash(_rec("gone")),
    }
    current = [
        _rec("keep"),                       # unchanged
        _rec("change", price="80.00"),      # updated
        _rec("brand-new"),                  # new
    ]
    changes = detect_changes(previous, current)
    assert changes.new == ["brand-new"]
    assert changes.updated == ["change"]
    assert changes.unchanged == ["keep"]
    assert changes.removed == ["gone"]


# -- crawl state persistence ---------------------------------------------
def test_crawl_state_round_trip(tmp_path):
    path = str(tmp_path / "state.json")
    state = CrawlState(store="townteam")
    records = [_rec("a"), _rec("b")]
    for r in records:
        r["content_hash"] = content_hash(r)
    first = state.update_from(records)
    assert first.summary()["new"] == 2
    state.save(path)

    reloaded = CrawlState.load(path, "townteam")
    assert set(reloaded.products.keys()) == {"a", "b"}

    # A second crawl with one changed product reports exactly one update.
    changed = [_rec("a", price="50.00"), _rec("b")]
    for r in changed:
        r["content_hash"] = content_hash(r)
    second = reloaded.update_from(changed)
    assert second.summary() == {"new": 0, "updated": 1, "unchanged": 1, "removed": 0}


def test_crawl_state_tracks_high_water_mark(tmp_path):
    state = CrawlState(store="s")
    r = _rec("a")
    r["source_updated_at"] = "2026-05-20T10:00:00Z"
    r["content_hash"] = content_hash(r)
    state.update_from([r])
    assert state.updated_at_max == "2026-05-20T10:00:00Z"
