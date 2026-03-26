import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path


def discover_collections(base_url: str):
    collections_url = urljoin(base_url, "/collections")

    resp = requests.get(collections_url, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    collection_urls = set()
    collection_urls.add(base_url)

    for a in soup.select("a[href^='/collections/']"):
        href = a.get("href")

        if href in ["/collections/all", "/collections/all-products"]:
            continue

        full_url = urljoin(base_url, href)
        collection_urls.add(full_url)

    return sorted(collection_urls)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python discover_collections.py <base_url>")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")

    collections = discover_collections(base_url)

    domain = urlparse(base_url).netloc.replace(".", "_")

    output_file = f"collections.txt"

    with open(output_file, "w", encoding="utf-8") as f:
        for url in collections:
            f.write(url + "\n")

    print(f"[+] {base_url}: discovered {len(collections)} collections")
