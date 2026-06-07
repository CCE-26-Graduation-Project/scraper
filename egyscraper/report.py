"""Aggregate per store output into one yield table.

Scans the output directory for each store's products.jsonl (and crawl_report.json
when present) and prints a sorted yield table with a total, automating the
summary you would otherwise compile by hand.

    python -m egyscraper.report
    python -m egyscraper.report --dir data
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List


def _count_lines(path: str) -> int:
    n = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n


def collect(output_dir: str) -> List[Dict]:
    """Return a per store summary list sorted by product count, descending."""
    rows: List[Dict] = []
    if not os.path.isdir(output_dir):
        return rows
    for slug in sorted(os.listdir(output_dir)):
        store_dir = os.path.join(output_dir, slug)
        jsonl = os.path.join(store_dir, "products.jsonl")
        if not os.path.isfile(jsonl):
            continue
        row = {"store": slug, "products": _count_lines(jsonl)}
        report = os.path.join(store_dir, "crawl_report.json")
        if os.path.isfile(report):
            try:
                with open(report, encoding="utf-8") as fh:
                    data = json.load(fh)
                row["requests"] = data.get("requests_made")
                row["failures"] = data.get("failures")
                row["duration_s"] = data.get("duration_seconds")
            except (ValueError, OSError):
                pass
        rows.append(row)
    rows.sort(key=lambda r: r["products"], reverse=True)
    return rows


def render(rows: List[Dict]) -> str:
    if not rows:
        return "no store output found"
    width = max(len(r["store"]) for r in rows)
    lines = [f"{'store'.ljust(width)}  products  requests  failures  duration_s"]
    total = 0
    for r in rows:
        total += r["products"]
        lines.append(
            f"{r['store'].ljust(width)}  "
            f"{str(r['products']).rjust(8)}  "
            f"{str(r.get('requests', '-')).rjust(8)}  "
            f"{str(r.get('failures', '-')).rjust(8)}  "
            f"{str(r.get('duration_s', '-')).rjust(10)}"
        )
    lines.append(f"{'TOTAL'.ljust(width)}  {str(total).rjust(8)}")
    return "\n".join(lines)


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate per store crawl yields.")
    parser.add_argument("--dir", default=os.getenv("OUTPUT_DIR", "data"))
    args = parser.parse_args(argv)
    print(render(collect(args.dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
