import subprocess
import sys
from urllib.parse import urlparse
from pathlib import Path
from load_products import insert_all_products

with open("base_urls.txt", "r", encoding="utf-8") as f:
    sites = [line.strip() for line in f if line.strip()]

Path("products").mkdir(exist_ok=True)


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
    
    collections_file = f"collections.txt"
    output_file = f"products/{domain}_products.json"

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

print("\nAll sites processed successfully")

# Load products to database
print("\nLoading products to database...")
insert_all_products()
