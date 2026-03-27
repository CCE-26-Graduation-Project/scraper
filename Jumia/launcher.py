import json
import importlib.util
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List


ROOT_DIR = Path(__file__).resolve().parent
SCRAPY_PROJECT_DIR = ROOT_DIR / "ecom_crawler"
OUTPUTS_DIR = ROOT_DIR / "outputs"
LOG_FILE = ROOT_DIR / "crawl_report.log"
SITE_TIMEOUT_SECONDS = 21600
SCRAPY_PYTHON = ROOT_DIR / ".venv" / "Scripts" / "python.exe"

SITE_RUNTIME_OVERRIDES: Dict[str, Dict[str, str]] = {
    "jumia": {
        "CLOSESPIDER_TIMEOUT": "21600",
        "CLOSESPIDER_PAGECOUNT": "200000",
        "DEPTH_LIMIT": "0",
    },
    "tiehouse": {
        "CLOSESPIDER_TIMEOUT": "120",
        "CLOSESPIDER_PAGECOUNT": "300",
        "DEPTH_LIMIT": "5",
    }
}

ERROR_PATTERNS: Dict[str, str] = {
    "dns_failure": "DNS lookup failed",
    "http_403": "response_status_count/403",
    "http_429": "response_status_count/429",
    "captcha_or_challenge": "captcha",
    "blocked_or_forbidden": "forbidden",
    "retry_exhausted": "Gave up retrying",
    "timeout": "Closing spider (closespider_timeout)",
}

SITES: List[str] = [
    "jumia",
]


def setup_logger() -> logging.Logger:
    """Configure file and console logging for the launcher run."""
    logger = logging.getLogger("crawl_launcher")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def ensure_directories() -> None:
    """Create required output directory if missing."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


def check_runtime_dependencies() -> None:
    """Fail fast with a clear message if required runtime packages are missing."""
    if SCRAPY_PYTHON.exists():
        check_cmd = [str(SCRAPY_PYTHON), "-c", "import scrapy"]
    else:
        check_cmd = [sys.executable, "-c", "import scrapy"]

    try:
        subprocess.run(check_cmd, check=True, capture_output=True, text=True)
        return
    except Exception:
        raise SystemExit(
            "Missing dependency: scrapy. Install it with:\n"
            f"{str(SCRAPY_PYTHON) if SCRAPY_PYTHON.exists() else sys.executable} -m pip install scrapy"
        )


def count_items_in_json(file_path: Path) -> int:
    """Count item records in a JSON array output file."""
    if not file_path.exists():
        return 0

    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        return 0
    except Exception:
        return 0


def run_site_crawl(site: str, logger: logging.Logger) -> Dict[str, object]:
    """Run one site crawl and return execution metrics for summary reporting."""
    date_stamp = datetime.now().strftime("%Y%m%d")
    output_file = OUTPUTS_DIR / f"{site}_{date_stamp}.json"

    python_bin = str(SCRAPY_PYTHON) if SCRAPY_PYTHON.exists() else sys.executable

    command = [
        python_bin,
        "-m",
        "scrapy",
        "crawl",
        "universal",
        "-a",
        f"site={site}",
    ]

    for key, value in SITE_RUNTIME_OVERRIDES.get(site, {}).items():
        command.extend(["-s", f"{key}={value}"])

    command.extend(
        [
        "-O",
        str(output_file),
        ]
    )

    logger.info("Starting crawl for site=%s", site)
    start = time.perf_counter()

    try:
        completed = subprocess.run(
            command,
            cwd=str(SCRAPY_PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=SITE_TIMEOUT_SECONDS,
            check=False,
        )
        elapsed = round(time.perf_counter() - start, 2)
        output_text = (completed.stdout or "") + "\n" + (completed.stderr or "")

        if completed.returncode != 0:
            categories = classify_failure_categories(output_text)
            logger.error("Site crawl failed for %s (exit=%s)", site, completed.returncode)
            if categories:
                logger.error("Failure categories for %s: %s", site, ", ".join(categories))
            if completed.stderr:
                logger.error("stderr for %s: %s", site, completed.stderr.strip())
            return {
                "site": site,
                "status": "Fail",
                "items": 0,
                "seconds": elapsed,
                "output": str(output_file),
                "failure_categories": categories,
            }

        items = count_items_in_json(output_file)
        categories = classify_failure_categories(output_text)
        if categories:
            logger.warning("Completed crawl for %s with warning categories: %s", site, ", ".join(categories))
        logger.info("Completed crawl for %s with %s items in %s seconds", site, items, elapsed)
        return {
            "site": site,
            "status": "Success",
            "items": items,
            "seconds": elapsed,
            "output": str(output_file),
            "failure_categories": categories,
        }

    except subprocess.TimeoutExpired:
        elapsed = round(time.perf_counter() - start, 2)
        logger.error("Site crawl timed out for %s after %s seconds", site, elapsed)
        return {
            "site": site,
            "status": "Fail",
            "items": 0,
            "seconds": elapsed,
            "output": str(output_file),
            "failure_categories": ["launcher_timeout"],
        }
    except Exception as exc:
        elapsed = round(time.perf_counter() - start, 2)
        logger.exception("Unexpected launcher error for %s: %s", site, exc)
        return {
            "site": site,
            "status": "Fail",
            "items": 0,
            "seconds": elapsed,
            "output": str(output_file),
            "failure_categories": ["launcher_exception"],
        }


def classify_failure_categories(output_text: str) -> List[str]:
    """Return normalized failure/retry categories found in Scrapy output."""
    lower = output_text.lower()
    categories: List[str] = []
    for category, needle in ERROR_PATTERNS.items():
        if needle.lower() in lower:
            categories.append(category)
    return categories


def print_summary(results: List[Dict[str, object]]) -> None:
    """Print terminal summary table for all crawls."""
    headers = ["Site Name", "Status", "Items", "Time (s)", "Notes"]
    rows = [
        [
            str(r["site"]),
            str(r["status"]),
            str(r["items"]),
            f"{r['seconds']:.2f}",
            ",".join(r.get("failure_categories", [])) or "-",
        ]
        for r in results
    ]

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(row_values: List[str]) -> str:
        return " | ".join(value.ljust(col_widths[i]) for i, value in enumerate(row_values))

    separator = "-+-".join("-" * col_widths[i] for i in range(len(col_widths)))

    print("\nCRAWL SUMMARY")
    print(fmt_row(headers))
    print(separator)
    for row in rows:
        print(fmt_row(row))


def main() -> None:
    logger = setup_logger()
    ensure_directories()
    check_runtime_dependencies()

    if not SCRAPY_PROJECT_DIR.exists():
        raise SystemExit(f"Scrapy project directory not found: {SCRAPY_PROJECT_DIR}")

    logger.info("Starting sequential crawl for %s sites", len(SITES))

    results: List[Dict[str, object]] = []
    for site in SITES:
        result = run_site_crawl(site, logger)
        results.append(result)

    successes = sum(1 for r in results if r["status"] == "Success")
    failures = len(results) - successes
    logger.info("Crawl batch complete. Success=%s, Fail=%s", successes, failures)

    print_summary(results)


if __name__ == "__main__":
    main()
