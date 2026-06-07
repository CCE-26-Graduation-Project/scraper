# egyscraper

Production scraping framework for the Intelligent Product Matching System. It
collects clothing and fashion products from Egyptian and international
retailers and emits one standardized record per product, ready for CLIP
embedding and PostgreSQL plus pgvector ingestion.

This is a single unified Scrapy project. It was built around the working
Shopify extraction prototype; the earlier Jumia prototype and all generated
artifacts were removed in favour of a clean, tested foundation.

## What it produces

Every spider emits the same record, regardless of store or extraction
technique:

```json
{
  "product_id": "sha256 of merchant + platform id",
  "source": "townteam",
  "vendor": "Town Team",
  "brand": "Town Team",
  "brand_normalized": "town team",
  "title": "Oversized Cotton Hoodie",
  "description": "Heavyweight 100% cotton hoodie. Relaxed fit.",
  "category": "hoodies",
  "subcategory": "Hoodies",
  "gender": "men",
  "price": 799.00,
  "original_price": 999.00,
  "currency": "EGP",
  "availability": "in_stock",
  "sku": null,
  "barcode": null,
  "gtin": null,
  "image_urls": ["https://.../front.jpg", "https://.../back.jpg"],
  "main_image": "https://.../front.jpg",
  "product_url": "https://townteam.com/products/oversized-cotton-hoodie",
  "material": ["cotton"],
  "colors": ["Black", "Olive"],
  "sizes": ["S", "M"],
  "variants": [
    {"variant_id": "sha256...", "sku": "TT-HOOD-S-BLK", "barcode": "6224000000011",
     "size": "S", "color": "Black", "price": 799.00, "original_price": 999.00,
     "currency": "EGP", "available": true, "inventory_quantity": null}
  ],
  "attributes": {"platform": "shopify", "platform_product_id": 7421234567890},
  "content_hash": "sha256 of the retrieval relevant content",
  "source_updated_at": "2026-05-20T10:00:00Z",
  "first_seen": "2026-06-01T12:00:00+00:00",
  "last_seen": "2026-06-01T12:00:00+00:00",
  "scraped_at": "2026-06-01T12:00:00+00:00"
}
```

Money is `Decimal`, serialized as a true JSON number (no float). Each product
keeps its full `variants` list rather than collapsing to one price; the product
level `price` is the lowest variant price. Category, gender and colours are
normalized across Arabic and English. `content_hash`, `first_seen` and
`last_seen` support incremental re crawls.

## Installation

Requires Python 3.10 or newer and Scrapy 2.13 or newer (the project uses the
async `start()` seed method introduced in 2.13).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running spiders

Crawl one store by its slug (slugs live in `egyscraper/stores/shopify_stores.py`):

```bash
scrapy crawl shopify -a store=townteam
```

Crawl any Shopify store by url, no registration needed:

```bash
scrapy crawl shopify -a base_url=https://example.com -a slug=example
```

For a store that disables the catalog wide endpoint but serves per collection
JSON, discover and crawl collections instead:

```bash
scrapy crawl shopify -a store=townteam -a use_collections=true
```

The Shopify spider also falls back to collection discovery automatically when
the store wide `/products.json` comes back empty, blocked, or missing, so a
store like that is recovered without any flag.

## Crawling structured custom stores (JSON LD)

Many non Shopify stores embed schema.org Product data on each product page. The
generic `jsonld` spider walks a store's sitemap, fetches product pages, and
extracts that structured data into the same schema, with no per store parsing
code, only a sitemap url (defaults to `/sitemap.xml`) and a regex that matches
product urls:

```bash
scrapy crawl jsonld -a store=decathlon
scrapy crawl jsonld -a base_url=https://defacto.com.eg -a slug=defacto -a product_pattern="/p/"
scrapy crawl jsonld -a base_url=https://example.com -a slug=example \
    -a sitemap=https://example.com/sitemap_products.xml -a product_pattern="/product/"
```

The spider handles both a single schema.org `Product` and a `ProductGroup`
(the standard shape for a product that varies by colour or size); a
ProductGroup is expanded into one record whose variants carry per option sku,
price and availability. Decathlon Egypt is verified and runnable with
`-a store=decathlon`.

## Running many stores at once

The runner crawls each store in its own subprocess, so one store failing,
hanging, or being blocked never stops the others. It prints a summary at the
end listing which stores succeeded and which failed.

```bash
python -m egyscraper.run --all          # every confirmed Shopify store
python -m egyscraper.run --candidates   # confirmed plus likely candidates
python -m egyscraper.run --store townteam mitcha
```

## Output and exporting

Each store writes to its own folder under `data/`, so runs and re runs never
clobber each other:

```
data/<slug>/products.jsonl   one JSON record per line, flushed as it is scraped
data/<slug>/products.json    a JSON array, assembled when the spider closes
```

JSONL is written incrementally, which keeps memory flat for catalogs of tens
of thousands of products and means partial progress is always on disk if a run
is interrupted. Change the output root with the `OUTPUT_DIR` environment
variable.

Export goes through a small `Exporter` interface (`egyscraper/core/exporters.py`).
A documented `PostgresExporter` placeholder marks exactly where direct database
ingestion plugs in later, upserting on the deterministic `product_id` so re
crawls update rows rather than create duplicates. No pipeline or spider changes
are needed to add it.

## Adding a new Shopify store

Most boutique stores on the target list run on Shopify and need no code. Add an
entry to `egyscraper/stores/shopify_stores.py`:

```python
ShopifyStore("newstore", "https://newstore.com")
```

Then `scrapy crawl shopify -a store=newstore`. To check whether a site is
Shopify, open `https://thesite.com/products.json` in a browser; a JSON list of
products means yes.

## Adding a non Shopify store

1. Identify the best extraction source using the priority order: public API,
   mobile API, GraphQL, embedded JSON, JSON LD, server rendered HTML, browser
   automation as a last resort. The recommended source per target store is in
   `egyscraper/stores/classification.py`.
2. Add a spider under `egyscraper/spiders/`. Build records with
   `core.schema.empty_product()`, assign a deterministic id with
   `core.ids.product_id(...)`, and reuse the normalizers in `core.normalize`.
   For JSON LD use `core.jsonld`; for API and GraphQL endpoints use `core.api`.
3. Yield the record dict. The pipeline cleans, normalizes, validates, dedupes,
   and exports it automatically.

## Store coverage

`python -m egyscraper.stores.classification` prints how the full target list
maps to platforms and extraction techniques. Platform guesses for stores not
yet implemented are marked `verify` and must be confirmed against the live site
before a spider is written.

## Configuration

Most operational knobs read from the environment so you need not edit code:

`CONCURRENT_REQUESTS`, `CONCURRENT_REQUESTS_PER_DOMAIN`, `DOWNLOAD_DELAY`,
`RETRY_TIMES`, `HTTPCACHE_ENABLED`, `ROBOTSTXT_OBEY`, `LOG_LEVEL`, `OUTPUT_DIR`,
`PROXY_URL`, `EXPORT_JSON_ARRAY` (set false to skip the array file on very large
catalogs), `EXPORT_FLUSH_EVERY`.

AutoThrottle, retry on transient errors, user agent rotation, an inert proxy
hook, and commented Playwright handlers are all configured in
`egyscraper/settings.py`. Proxy, residential proxy, and CAPTCHA integration
points are present as documented placeholders.

## Testing

The suite runs from a fresh clone with no network access:

```bash
pytest
```

It covers deterministic product and variant ids, every normalizer (Arabic and
English), the schema helpers, Decimal money, the variant aware Shopify mapper,
the embedding text builder, the change tracking foundation, the exporters, the
spider request and pagination logic, and each pipeline stage.

## Architecture overview

```
egyscraper/
  settings.py          production settings (throttle, retry, cache, rotation, export)
  items.py             ProductItem mirroring the standardized schema
  pipelines.py         clean, price norm, category norm, validate, change track, dedupe, export
  middlewares.py       user agent rotation, proxy hook (inert by default)
  run.py               fault isolating multi store runner
  core/
    schema.py          the canonical variant aware record, required fields, ordering
    ids.py             deterministic SHA256 product and variant ids
    normalize.py       multilingual category, gender, colour, Decimal price, fashion gate
    jsonld.py          schema.org Product extraction from HTML
    api.py             REST, mobile and GraphQL request helpers
    shopify.py         variant aware Shopify products.json to schema mapper
    jsonld_mapper.py   schema.org Product node to schema mapper
    embedding_text.py  compact CLIP text builder (excludes variant noise)
    change_tracking.py content hash, change detection, per store crawl state
    exporters.py       Decimal safe JSONL and JSON array exporters, PostgreSQL placeholder
  spiders/
    shopify.py         generic Shopify spider (store wide + collection fallback)
    jsonld.py          generic sitemap plus JSON LD spider for custom stores
  stores/
    shopify_stores.py  registry of Shopify stores and slugs
    classification.py  all target stores by platform and extraction source
tests/                 pytest suite plus a Shopify fixture
```

### Fault tolerance

A bad product is logged and skipped, never fatal. A failed request is retried,
then logged via the spider errback. A failed store is isolated by the runner's
subprocess boundary. Accepted records are flushed to disk immediately, so an
interrupted run keeps everything scraped up to that point.

### Why this shape

The crawler stays decoupled from embedding and database concerns. It writes
clean, deterministic, schema stable JSON; a separate loader generates CLIP
embeddings and inserts into PostgreSQL. The `Exporter` seam lets that move
inline later without disturbing the crawl path.

## Project scope: Clothing and Footwear only

The system retains only clothing and footwear products. Everything else
(accessories, sports equipment, electronics, home goods) is rejected before
export. This happens automatically in the `ScopeFilterPipeline` (priority 410)
which runs after category normalisation but before validation, change tracking,
deduplication, and export. No spider needs store-specific filtering logic.

### Scope types
| Accepted | `scope_type` |
|---|---|
| T-shirts, shirts, jackets, jeans, dresses, activewear, underwear, socks, swimwear, sleepwear, tracksuits, traditional garments | `clothing` |
| Sneakers, boots, sandals, heels, flats, loafers, slippers, athletic footwear | `footwear` |

### Every exported record carries a scope field
```json
{"scope": {"is_supported": true, "scope_type": "clothing"}}
```

### Rejection breakdown in every crawl report
```
scope: 2800 seen, 1150 accepted, 1650 rejected
rejection breakdown: accessory: 890, sports_equipment: 620, home_goods: 82, electronics: 58
```

### Audit existing crawled data
```bash
python -m egyscraper.scope_audit data/
python -m egyscraper.scope_audit data/ --apply   # rewrite jsonl files in place
```
