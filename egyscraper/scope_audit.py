"""Scope audit CLI.

Scans existing products.jsonl files and estimates the impact of the scope
filter on already-crawled data, so you know how much of each store's catalog
would be retained or rejected before re-running.

Usage
-----
    # dry run: print a table of retained vs rejected per store
    python -m egyscraper.scope_audit data/

    # also rewrite each products.jsonl keeping only in-scope records
    python -m egyscraper.scope_audit data/ --apply

    # output a CSV instead of a table
    python -m egyscraper.scope_audit data/ --csv
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List

from .core.scope import classify_record


def _iter_records(path: Path):
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass


def audit_store(jsonl_path: Path) -> Dict:
    accepted = 0
    rejected: Dict[str, int] = {}
    total = 0
    for record in _iter_records(jsonl_path):
        total += 1
        scope = classify_record(record)
        if scope["is_supported"]:
            accepted += 1
        else:
            reason = scope.get("rejection_reason", "out_of_scope")
            rejected[reason] = rejected.get(reason, 0) + 1
    return {
        "total": total,
        "accepted": accepted,
        "rejected": sum(rejected.values()),
        "rejection_breakdown": rejected,
    }


def apply_filter(jsonl_path: Path) -> int:
    """Rewrite a products.jsonl keeping only in-scope records. Returns kept count."""
    tmp = jsonl_path.with_suffix(".jsonl.scope_tmp")
    kept = 0
    with tmp.open("w", encoding="utf-8") as out:
        for record in _iter_records(jsonl_path):
            scope = classify_record(record)
            if scope["is_supported"]:
                record["scope"] = scope
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
    shutil.move(str(tmp), str(jsonl_path))
    return kept


def _print_table(rows: List[dict], csv_mode: bool) -> None:
    sep = "," if csv_mode else "  "
    header = ["store", "total", "retained", "rejected", "pct_retained", "breakdown"]
    if csv_mode:
        print(",".join(header))
    else:
        print(f"{'store':<22} {'total':>7} {'retained':>9} {'rejected':>8}  {'%':>5}  breakdown")
        print("-" * 90)
    total_all = total_ret = total_rej = 0
    for r in rows:
        pct = round(100 * r["accepted"] / r["total"], 1) if r["total"] else 0.0
        bd = "; ".join(f"{k}: {v}" for k, v in sorted(r["rejection_breakdown"].items()))
        total_all += r["total"]
        total_ret += r["accepted"]
        total_rej += r["rejected"]
        if csv_mode:
            print(f"{r['store']},{r['total']},{r['accepted']},{r['rejected']},{pct},{bd}")
        else:
            print(f"{r['store']:<22} {r['total']:>7} {r['accepted']:>9} {r['rejected']:>8}  {pct:>4}%  {bd}")
    if not csv_mode:
        print("-" * 90)
        grand_pct = round(100 * total_ret / total_all, 1) if total_all else 0.0
        print(f"{'TOTAL':<22} {total_all:>7} {total_ret:>9} {total_rej:>8}  {grand_pct:>4}%")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Estimate scope filter impact on existing crawl data")
    parser.add_argument("data_dir", help="root data directory (contains per store subdirs)")
    parser.add_argument("--apply", action="store_true",
                        help="rewrite each products.jsonl keeping only in-scope records")
    parser.add_argument("--csv", action="store_true", help="output CSV instead of table")
    args = parser.parse_args(argv)

    data_root = Path(args.data_dir)
    if not data_root.is_dir():
        print(f"error: {data_root} is not a directory", file=sys.stderr)
        sys.exit(1)

    rows = []
    for store_dir in sorted(data_root.iterdir()):
        if not store_dir.is_dir():
            continue
        jsonl = store_dir / "products.jsonl"
        if not jsonl.exists():
            continue
        slug = store_dir.name
        result = audit_store(jsonl)
        result["store"] = slug
        rows.append(result)
        if args.apply:
            kept = apply_filter(jsonl)
            print(f"applied: {slug}: {kept} records kept")

    if rows:
        _print_table(rows, args.csv)
    else:
        print("no products.jsonl files found under", data_root)


if __name__ == "__main__":
    main()
