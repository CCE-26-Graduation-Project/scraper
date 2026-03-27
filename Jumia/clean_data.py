import argparse
import csv
import json
import re
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = ROOT_DIR / "outputs"
DEFAULT_CSV_PATH = ROOT_DIR / "master_products.csv"
DEFAULT_SQLITE_PATH = ROOT_DIR / "master_products.db"

PRICE_REGEX = re.compile(r"\d[\d,]*(?:\.\d+)?")
STOPWORDS = {
    "men",
    "women",
    "woman",
    "man",
    "kids",
    "kid",
    "boy",
    "girl",
    "fashion",
    "shirt",
    "pants",
    "dress",
    "shoe",
    "shoes",
    "bag",
    "new",
}


def normalize_price(price_value: str) -> Optional[float]:
    """Extract first numeric value from price text and convert to float."""
    if not isinstance(price_value, str):
        return None

    match = PRICE_REGEX.search(price_value)
    if not match:
        return None

    number_str = match.group(0).replace(",", "")
    try:
        return float(number_str)
    except ValueError:
        return None


def is_valid_image_url(url: str, check_remote: bool = True, timeout: int = 6) -> bool:
    """Validate image URL format and optionally verify URL is reachable."""
    if not isinstance(url, str):
        return False

    url = url.strip()
    if not url or not url.startswith(("http://", "https://")):
        return False

    if not check_remote:
        return True

    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            return response.status < 400 and ("image" in content_type or "octet-stream" in content_type)
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return False


def extract_brand_from_url(url: str) -> str:
    """Infer brand-like token from URL host/path."""
    if not isinstance(url, str) or not url.strip():
        return ""

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname:
        parts = [p for p in hostname.split(".") if p and p not in {"www", "com", "eg", "co"}]
        if parts:
            return parts[-1].replace("-", " ").title()

    path_tokens = [p for p in parsed.path.split("/") if p]
    for token in path_tokens:
        cleaned = re.sub(r"[^A-Za-z]", "", token)
        if len(cleaned) >= 3:
            return cleaned.title()

    return ""


def extract_brand_from_title(title: str) -> str:
    """Infer brand from title by selecting the first meaningful token."""
    if not isinstance(title, str) or not title.strip():
        return ""

    for token in re.split(r"\s+", title.strip()):
        cleaned = re.sub(r"[^A-Za-z]", "", token)
        lowered = cleaned.lower()
        if len(cleaned) >= 3 and lowered not in STOPWORDS:
            return cleaned.title()
    return ""


def infer_brand(item: Dict[str, object]) -> str:
    """Return existing brand if present, otherwise infer from URL then title."""
    raw_brand = str(item.get("brand") or "").strip()
    if raw_brand:
        return raw_brand

    from_url = extract_brand_from_url(str(item.get("url") or ""))
    if from_url:
        return from_url

    return extract_brand_from_title(str(item.get("title") or ""))


def iter_source_records(input_dir: Path) -> Iterable[Dict[str, object]]:
    """Yield product records from all JSON files in input directory."""
    for json_file in sorted(input_dir.glob("*.json")):
        try:
            with json_file.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        yield row
        except Exception:
            continue


def clean_records(input_dir: Path, check_images: bool) -> List[Dict[str, object]]:
    """Transform raw JSON records into normalized cleaned product rows."""
    cleaned: List[Dict[str, object]] = []

    for item in iter_source_records(input_dir):
        title = str(item.get("title") or "").strip()
        price_raw = str(item.get("price") or "").strip()
        image_url = str(item.get("images") or "").strip()

        if not title:
            continue

        numeric_price = normalize_price(price_raw)
        if numeric_price is None:
            continue

        if not is_valid_image_url(image_url, check_remote=check_images):
            continue

        url_value = str(item.get("url") or "").strip()
        category = str(item.get("category") or "").strip()
        rating = str(item.get("rating") or "").strip()

        brand = infer_brand(item)

        cleaned.append(
            {
                "site": str(item.get("site") or "").strip(),
                "url": url_value,
                "title": title,
                "brand": brand,
                "category": category,
                "rating": rating,
                "price_original": price_raw,
                "price": numeric_price,
                "currency": "EGP",
                "images": image_url,
            }
        )

    return cleaned


def export_csv(records: List[Dict[str, object]], csv_path: Path) -> None:
    """Write cleaned records to CSV for analysis workflows."""
    fields = [
        "site",
        "url",
        "title",
        "brand",
        "category",
        "rating",
        "price_original",
        "price",
        "currency",
        "images",
    ]

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def export_sqlite(records: List[Dict[str, object]], db_path: Path) -> None:
    """Write cleaned records to SQLite for backend usage."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                site TEXT,
                url TEXT,
                title TEXT,
                brand TEXT,
                category TEXT,
                rating TEXT,
                price_original TEXT,
                price REAL,
                currency TEXT,
                images TEXT
            )
            """
        )
        cursor.execute("DELETE FROM products")

        cursor.executemany(
            """
            INSERT INTO products (
                site, url, title, brand, category, rating,
                price_original, price, currency, images
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    str(r.get("site") or ""),
                    str(r.get("url") or ""),
                    str(r.get("title") or ""),
                    str(r.get("brand") or ""),
                    str(r.get("category") or ""),
                    str(r.get("rating") or ""),
                    str(r.get("price_original") or ""),
                    float(r.get("price") or 0.0),
                    "EGP",
                    str(r.get("images") or ""),
                )
                for r in records
            ],
        )

        conn.commit()
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    """CLI options for transform/export flow."""
    parser = argparse.ArgumentParser(description="Clean e-commerce crawl outputs and export datasets.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory containing JSON crawl outputs.")
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH), help="Output path for CSV export.")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_SQLITE_PATH), help="Output path for SQLite export.")
    parser.add_argument(
        "--skip-image-check",
        action="store_true",
        help="Skip remote URL check for images (faster).",
    )
    parser.add_argument("--no-csv", action="store_true", help="Disable CSV export.")
    parser.add_argument("--no-sqlite", action="store_true", help="Disable SQLite export.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir).resolve()
    csv_path = Path(args.csv_path).resolve()
    sqlite_path = Path(args.sqlite_path).resolve()

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    records = clean_records(input_dir=input_dir, check_images=not args.skip_image_check)

    if not args.no_csv:
        export_csv(records, csv_path)
    if not args.no_sqlite:
        export_sqlite(records, sqlite_path)

    print(f"Clean records: {len(records)}")
    if not args.no_csv:
        print(f"CSV exported: {csv_path}")
    if not args.no_sqlite:
        print(f"SQLite exported: {sqlite_path}")


if __name__ == "__main__":
    main()
