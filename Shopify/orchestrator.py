import subprocess
import sys
from urllib.parse import urlparse
from pathlib import Path

# Output goes to the repo-wide Products folder, not Shopify/products.
# Path is computed relative to this file so it works regardless of CWD.
PRODUCTS_DIR = Path(__file__).resolve().parent.parent / "Products"

with open("base_urls.txt", "r", encoding="utf-8") as f:
    sites = [line.strip() for line in f if line.strip()]

PRODUCTS_DIR.mkdir(exist_ok=True)


for base_url in sites:
    print(f"\nProcessing {base_url}...")

    # 1. Discover collections
    subprocess.run(
        [sys.executable, "discover_collections.py", base_url],
        check=True
    )

    netloc = urlparse(base_url).netloc
    parts = netloc.split(".")

    if parts[0] == "shop" or parts[0] == "www":
        domain = parts[1]
    else:
        domain = parts[0]

    collections_file = "collections.txt"
    output_file = str(PRODUCTS_DIR / f"{domain}_products.json")

    # 2. Scrape products
    subprocess.run(
        [
            "scrapy",
            "crawl",
            "shopify_products",
            "-a",
            f"collections_file={collections_file}",
            "-O",
            output_file,
        ],
        check=True
    )

print(f"\nAll sites scraped. JSON files written to: {PRODUCTS_DIR}")
