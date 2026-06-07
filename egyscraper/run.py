"""Fault isolating multi store runner.

Each store is crawled in its own subprocess so one store crashing, hanging, or
being blocked cannot stop the others.  Log output is written to a per store
file under data/<slug>/ so the terminal stays readable (and VS Code's terminal
buffer does not overflow on large multi store runs).

Usage
-----
    python -m egyscraper.run --all               # every confirmed Shopify store
    python -m egyscraper.run --candidates        # confirmed + candidates
    python -m egyscraper.run --store townteam    # one store
    python -m egyscraper.run --store a b c       # several stores
    python -m egyscraper.run --all --parallel 3  # up to 3 stores concurrently
    python -m egyscraper.run --all --verbose     # stream logs to terminal too
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from .stores.shopify_stores import SHOPIFY_STORES, all_slugs, confirmed_slugs


# ── single store ─────────────────────────────────────────────────────────────

def crawl_store(
    slug: str,
    log_dir: Optional[Path] = None,
    verbose: bool = False,
    log_level: str = "INFO",
) -> bool:
    """Run one Shopify spider in an isolated subprocess.

    Scrapy output goes to data/<slug>/scrapy.log so it does not flood the
    terminal or VS Code's scroll buffer.  A one-line progress indicator is
    printed to the terminal instead.

    Returns True on clean exit.
    """
    print(f"  → {slug} …", flush=True, end=" ")

    # Build the command.
    cmd = [
        sys.executable, "-m", "scrapy", "crawl", "shopify",
        "-a", f"store={slug}",
        "-s", f"LOG_LEVEL={log_level}",
    ]

    # Redirect scrapy output to a log file to keep the terminal clean.
    store_log: Optional[Path] = None
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        store_log = log_dir / "scrapy.log"
        cmd += ["-s", f"LOG_FILE={store_log}"]

    try:
        if verbose or store_log is None:
            result = subprocess.run(cmd, check=False)
        else:
            # Capture stderr/stdout too (Scrapy may print to both before the
            # log file is opened).  Show them only on failure.
            result = subprocess.run(
                cmd, check=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        if result.returncode == 0:
            print("done", flush=True)
            return True
        print(f"FAILED (exit {result.returncode})", flush=True)
        if store_log:
            print(f"    log: {store_log}", flush=True)
        return False

    except Exception as exc:
        print(f"ERROR ({exc})", flush=True)
        return False


# ── parallel helper ───────────────────────────────────────────────────────────

def _run_parallel(slugs: List[str], max_workers: int, log_root: Path,
                   verbose: bool, log_level: str) -> Dict[str, bool]:
    """Run up to max_workers stores concurrently using threads (each thread
    owns one subprocess, so Python's GIL is not a bottleneck)."""
    results: Dict[str, bool] = {}
    lock = threading.Lock()
    semaphore = threading.Semaphore(max_workers)

    def worker(slug: str) -> None:
        with semaphore:
            ok = crawl_store(slug, log_dir=log_root / slug,
                             verbose=verbose, log_level=log_level)
            with lock:
                results[slug] = ok

    threads = [threading.Thread(target=worker, args=(s,), daemon=True) for s in slugs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# ── entry point ───────────────────────────────────────────────────────────────

def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Shopify spiders across stores, one per subprocess."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true",
                       help="all confirmed Shopify stores")
    group.add_argument("--candidates", action="store_true",
                       help="confirmed + candidate stores")
    group.add_argument("--store", nargs="+", metavar="SLUG",
                       help="specific store slug(s)")
    parser.add_argument("--parallel", type=int, default=1, metavar="N",
                        help="run up to N stores concurrently (default 1)")
    parser.add_argument("--verbose", action="store_true",
                        help="stream scrapy logs to the terminal (may cause OOM "
                             "in VS Code for large runs)")
    parser.add_argument("--log-level", default="WARNING",
                        help="scrapy log level written to the log file (default WARNING)")
    parser.add_argument("--data-dir", default="data",
                        help="root directory for output and logs (default data/)")
    args = parser.parse_args(argv)

    # Resolve slug list.
    if args.all:
        slugs = confirmed_slugs()
    elif args.candidates:
        slugs = all_slugs()
    else:
        slugs = args.store
        unknown = [s for s in slugs if s not in SHOPIFY_STORES]
        if unknown:
            print(f"unknown store slug(s): {unknown}", file=sys.stderr)
            return 2

    data_root = Path(args.data_dir)
    parallel = max(1, args.parallel)

    print(f"\negyscraper: running {len(slugs)} store(s) "
          f"({'parallel ' + str(parallel) if parallel > 1 else 'sequential'})")
    print(f"logs → {data_root}/<store>/scrapy.log\n")

    started = time.time()

    if parallel == 1:
        results = {
            slug: crawl_store(
                slug,
                log_dir=data_root / slug,
                verbose=args.verbose,
                log_level=args.log_level,
            )
            for slug in slugs
        }
    else:
        results = _run_parallel(
            slugs, parallel, data_root,
            verbose=args.verbose, log_level=args.log_level,
        )

    ok = [s for s, good in results.items() if good]
    failed = [s for s, good in results.items() if not good]
    elapsed = time.time() - started

    print(f"\n{'─'*48}")
    print(f"  stores attempted : {len(results)}")
    print(f"  succeeded        : {len(ok)}  {ok}")
    print(f"  failed           : {len(failed)}  {failed}")
    print(f"  elapsed          : {elapsed:.1f}s")
    print(f"{'─'*48}")
    print(f"\nResults: python -m egyscraper.report --dir {data_root}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
