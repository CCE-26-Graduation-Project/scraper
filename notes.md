# Technical Report: Egyptian Fashion Scraping Pipeline

## Overview

This project is a production-grade data pipeline for collecting, normalizing, and storing clothing and fashion product data from Egyptian and international retailers. It builds a standardized, searchable catalog with embeddings support for semantic search and recommendation.

**Core goal:** Crawl 40+ fashion stores, normalize their product data into a unified schema, compute embeddings per product/color combination, and load everything into a PostgreSQL database with delta-based incremental updates.

---

## 1. Orchestrator (`orchestrator.py`)

The orchestrator is the top-level entry point that coordinates the full pipeline end-to-end.

**What it does:**
1. Runs the Shopify scraper (legacy project under `Shopify/`)
2. Runs `egyscraper` across all registered stores
3. Calls `load_products` in delta mode to sync DB

**Key flags:**
```bash
python orchestrator.py                           # Full pipeline
python orchestrator.py --shopify-only            # Skip egyscraper
python orchestrator.py --skip-load               # Scrape only, no DB writes
python orchestrator.py --egyscraper-args "--parallel 3 --all"
```

**Design choice:** The orchestrator treats each sub-system as a subprocess. One sub-system failing (e.g., the legacy Shopify scraper) does not stop the rest of the pipeline.

---

## 2. Scrapers

### 2.1 Scrapy (Primary Framework)

[Scrapy](https://scrapy.org/) is the main scraping framework used in this project. It is an asynchronous, high-performance web crawling framework for Python.

**Why Scrapy:**
- Built-in async I/O (Twisted) — handles many concurrent requests without threads
- Item/Pipeline architecture separates extraction from processing
- Middleware system for request interception (user agents, proxies, retries)
- Built-in HTTP cache, auto-throttle, robots.txt support
- Subprocess-friendly — each spider run is an isolated process

**Project layout:**
```
egyscraper/
├── settings.py         # Scrapy configuration (throttle, retry, cache, user agents)
├── items.py            # ProductItem schema
├── pipelines.py        # 8-stage processing pipeline
├── middlewares.py      # User agent rotation, proxy hook
├── run.py              # Multi-store parallel runner
└── spiders/
    ├── shopify.py      # Generic Shopify spider
    └── jsonld.py       # Generic JSON-LD spider
```

#### Shopify Spider (`spiders/shopify.py`)

Shopify exposes a public `/products.json` endpoint that returns full product data as JSON — no HTML parsing required.

**Modes:**
1. **Store-wide (default):** Fetches `/products.json?page=N&limit=250` and paginates until empty (max 200 pages)
2. **Collection fallback:** If the store-wide endpoint is blocked or empty, falls back to fetching `/collections/<handle>/products.json` per collection

```bash
scrapy crawl shopify -a store=townteam
scrapy crawl shopify -a base_url=https://example.com -a slug=example
scrapy crawl shopify -a store=townteam -a use_collections=true
```

#### JSON-LD Spider (`spiders/jsonld.py`)

For non-Shopify stores that embed schema.org `Product` or `ProductGroup` JSON inside HTML `<script>` tags.

**Flow:**
1. Fetch store's `sitemap.xml`
2. Filter URLs matching a `product_pattern` regex
3. Fetch each product page
4. Extract and parse the first `<script type="application/ld+json">` block
5. Map via `core/jsonld_mapper.py`

```bash
scrapy crawl jsonld -a store=decathlon
```

---

### 2.2 Selenium (Browser Automation — Fallback)

[Selenium](https://www.selenium.dev/) is a browser automation library that drives a real browser (Chrome, Firefox). It is used as a last resort for stores that heavily rely on JavaScript rendering and cannot be scraped with static HTTP requests.

**When it's needed:**
- Stores with JS-rendered product grids (React/Vue/Angular SPAs)
- AJAX-loaded pagination
- Stores using anti-bot measures that require a real browser fingerprint

**Status in this project:** The `scrapy-playwright` integration points are present and documented in `settings.py` but commented out. The scope classifier and pipeline fully support products coming from browser-automated spiders — the extraction layer is pluggable.

---

### 2.3 Beautiful Soup (HTML Parsing — Utility)

[Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) is an HTML/XML parsing library. It is simpler than Scrapy's built-in selectors for one-off parsing tasks.

**Where it fits:**
- Parsing extracted JSON-LD blocks from raw HTML when the script tag needs cleanup
- Fallback HTML parsing in stores that have partial server-rendered content
- Utility parsing in non-Scrapy contexts (e.g., the legacy `Shopify/` project)

---

## 3. Item Pipeline (8 Stages)

After a spider yields a `ProductItem`, it passes through 8 ordered pipeline stages. Lower number = runs first.

```
200  CleaningPipeline              Strip whitespace, normalize lists, set main_image
300  PriceNormalizationPipeline    Parse prices to Decimal, normalize currency
400  CategoryNormalizationPipeline Backfill category/gender from all available fields
450  DeduplicationPipeline         Drop duplicates by product_id (dedup BEFORE scope check)
460  ScopeFilterPipeline           Accept clothing/footwear only; reject everything else
470  ValidationPipeline            Require: title, price, image_urls, product_url
480  ChangeTrackingPipeline        Compute content_hash; stamp first_seen / last_seen
900  ExportPipeline                Write to JSONL + JSON array under Products/
```

**Key design decisions:**
- Deduplication runs before scope filtering so rejection stats reflect unique products
- A bad item is logged and skipped — never fatal to the crawl
- Records are flushed to disk immediately (partial progress survives interrupts)
- ExportPipeline keeps the previous output file if the current run produced 0 records (protects against transient blocks wiping good data)

---

## 3.1 Output Format: JSONL vs JSON Array

The `ExportPipeline` (stage 900) writes two files per store and then removes one of them. Understanding why both formats exist, and which one survives, matters for anything that reads the output.

### What is JSONL (JSON Lines)?

JSONL is a text file where every line is a complete, self-contained JSON object:

```
{"title": "Black Hoodie", "price": 200, "colors": ["Black"], ...}
{"title": "White Tee", "price": 150, "colors": ["White"], ...}
{"title": "Navy Joggers", "price": 299, "colors": ["Navy"], ...}
```

There is no outer wrapper — no `[` at the start, no `]` at the end, no commas between lines. Each line stands alone.

### What is a JSON array?

A JSON array wraps all records inside a single `[...]` structure:

```json
[
  {"title": "Black Hoodie", "price": 200, "colors": ["Black"], ...},
  {"title": "White Tee", "price": 150, "colors": ["White"], ...},
  {"title": "Navy Joggers", "price": 299, "colors": ["Navy"], ...}
]
```

This is what most people think of when they hear "a JSON file". It is valid JSON and can be loaded in one call with `json.load()`.

### Why the scraper writes JSONL first

The scraper processes products one by one as Scrapy yields them from the network — it does not have all 2,000 products in memory at once. JSONL matches this streaming model naturally:

- **Memory is flat.** The scraper appends one line at a time. A catalog of 10,000 products uses no more memory than a catalog of 10.
- **Crash safety.** The exporter flushes to disk every 200 records (`EXPORT_FLUSH_EVERY`). If the spider crashes at product 800, records 1–800 are already safely on disk in the `.jsonl` file. A JSON array cannot be partially written — a half-written `[...]` is not valid JSON and cannot be read at all.
- **Atomic write via temp file.** The exporter always writes to `{slug}_products.jsonl.tmp` and only renames it to the final path once the run completes cleanly. This means the previous good file is never overwritten by a partial run. If the rename itself fails (e.g. Windows file lock), the data is still intact in the `.tmp` file and the error message tells you exactly how to recover it.

### Why a JSON array is also built

Once the JSONL file is complete, `_build_json_array()` reads it line by line and wraps it into a `.json` file. This exists purely for convenience:

- **Human inspection.** VS Code, browsers, and most JSON viewers render a `[...]` file correctly. A JSONL file looks like broken JSON to these tools.
- **Simple loading in scripts.** `json.load(open('townteam_products.json'))` returns a Python list immediately, with no line-splitting or parsing loop.
- **Compatibility.** Downstream scripts written before JSONL was introduced (e.g. `load_products.py`, `sync_products.py`) expect a JSON array.

### What you actually find in `Products/` after a run

```
Products/
  townteam_products.json      ← the one you use (JSON array, survives)
  townteam_products.jsonl     ← deleted after array is built
```

After a **successful** run: only the `.json` file remains. The `.jsonl` is deleted once the array is assembled (see `ExportPipeline.close_spider`).

After a **crashed or interrupted** run: only the `.jsonl` file may exist, containing however many records were flushed before the crash. It can be read line by line and is valid data — the array was just never assembled.

If the **atomic rename fails** (Windows file lock from VS Code or Windows Defender): the complete data is in `{slug}_products.jsonl.tmp`. The log prints the exact `move` command to recover it manually.

### Empty-run protection

If the scraper runs successfully but yields **zero products** (the store blocked all requests, or the endpoint returned nothing), the exporter detects `count == 0` and deliberately skips the rename — leaving the previous non-empty `.json` file untouched. This prevents a transient block from wiping a good catalog that was scraped cleanly last time.

---

## 4. Canonical Product Schema (`core/schema.py`)

Every spider, regardless of store or extraction method, emits the same record structure.

**Top-level fields:**
- `product_id` — deterministic SHA256 hash (never random)
- `source` — store slug (e.g., `"townteam"`)
- `title`, `description`, `vendor`, `brand`, `brand_normalized`
- `category`, `subcategory`, `gender` — normalized English values
- `price`, `original_price`, `currency` — Decimal, never float
- `availability` — `"in_stock"` / `"out_of_stock"`
- `sku`, `barcode`, `gtin`
- `image_urls`, `main_image`, `product_url`
- `material`, `colors`, `sizes` — normalized lists
- `variants` — full variant list (see below)
- `attributes` — platform-specific metadata (Shopify tags, handle, etc.)
- `content_hash` — SHA256 of retrieval-relevant fields (for change detection)
- `scope` — `{is_supported: bool, scope_type: str}`
- `scraped_at`, `first_seen`, `last_seen`

**Variant structure (per item in `variants[]`):**
```json
{
  "variant_id": "sha256(...)",
  "platform_variant_id": "7421234567890",
  "sku": "TT-HOOD-S-BLK",
  "barcode": "6224000000011",
  "size": "S",
  "color": "Black",
  "price": 799.00,
  "original_price": 999.00,
  "currency": "EGP",
  "available": true,
  "inventory_quantity": null
}
```

**Why variants are never collapsed:** The product-level price is derived (minimum of variant prices) but the full variants list is always preserved. This ensures downstream systems have access to per-size/per-color pricing and availability.

---

## 5. Deterministic Identifiers (`core/ids.py`)

**Problem:** A product re-scraped on a later run must get the same ID, or re-scrapes create duplicates instead of updates.

**Solution:** SHA256 hash with a fallback hierarchy:

```
Product ID = SHA256( merchant + platform_product_id )
           ↓ fallback
           SHA256( merchant + handle )
           ↓ fallback
           SHA256( merchant + product_url )

Variant ID = SHA256( product_id + barcode )
           ↓ fallback
           SHA256( product_id + gtin )
           ↓ fallback
           SHA256( product_id + sku )
           ↓ fallback
           SHA256( product_id + size + color )
           ↓ last resort
           SHA256( product_id + index )
```

Stronger identifiers (platform IDs, barcodes) are preferred because they remain stable across URL changes and store restructuring.

---

## 6. Multilingual Normalization (`core/normalize.py`)

Stores publish data in Arabic, English, or both. Normalization converts everything to canonical English values.

**Category normalization:**
- ~20 canonical categories (t-shirts, hoodies, jeans, dresses, shoes, etc.)
- Rules ordered specific → general; first match wins
- English keywords use word boundaries; Arabic uses substring matching

**Gender normalization:**
- Output: `men`, `women`, `kids`, `unisex`, or `""`

**Color normalization:**
- 18 canonical colors (Black, White, Navy, Blue, Gray, etc.)
- Finds the first match in a combined string (`"BLUE / WHITE"` → `Blue`)
- Unknown colors are returned title-cased rather than dropped

**Price parsing:**
- Handles messy formats: `"799 EGP"`, `"99.99$"`, `"999,00€"`
- Both comma and period as decimal separator
- Always returns `Decimal(str(...))` — never `float`

**Material extraction:**
- Recognizes ~15 materials (cotton, polyester, wool, silk, leather, etc.)
- Case-insensitive substring matching across all product text fields

---

## 7. Scope Classification (`core/scope.py`)

Single source of truth for what belongs in the system: **Clothing and Footwear only**.

**In-scope:**
- `clothing`: T-shirts, shirts, jackets, jeans, dresses, swimwear, underwear, socks, activewear, abayas, jalabiya
- `footwear`: Sneakers, boots, sandals, heels, flats, loafers, slippers

**Out-of-scope (with reason codes):**
- `accessory`: Bags, belts, watches, jewelry, scarves, hats
- `sports_equipment`: Dumbbells, tents, bikes, rackets, yoga mats
- `electronics`: Headphones, smartwatches, chargers, phones
- `home_goods`: Bottles, towels, furniture, kitchenware

**Two-pass strategy:**
1. Primary: classify from `category`, `title`, `subcategory`, `tags`, `breadcrumbs`
2. Fallback: scan `description` with a restricted keyword set (guards against stores like Lablanca that use model names like "Vivienne" as titles)

**Pipeline integration:** `ScopeFilterPipeline` (priority 460) is the single point where products are accepted or rejected. It increments Scrapy stats with rejection breakdowns for health reporting.

---

## 8. Change Tracking (`core/change_tracking.py`)

Enables efficient re-crawls: only products whose content actually changed get re-embedded and re-inserted.

**Content hash:**

A SHA256 fingerprint of retrieval-relevant fields:
```
title, description, category, gender, brand,
price, original_price, availability, image_urls,
+ variant skus, prices, availability
```

Same product, same data → same hash → skip on re-crawl.

**ChangeSet detection:**

Compares previous run's hashes against current scrape:
- `new` — ID not in old state → insert + embed
- `updated` — ID present, hash changed → delete old, insert fresh + re-embed
- `unchanged` — ID present, hash identical → skip entirely
- `removed` — ID in old, absent from new → delete or mark out-of-stock

**CrawlState:**

A JSON file per store persisting the hash index across runs:
```json
{
  "store": "townteam",
  "updated_at_max": "2026-05-20T10:00:00Z",
  "products": {
    "product-id-1": {
      "content_hash": "abc123...",
      "last_seen": "2026-06-01T12:00:00Z"
    }
  }
}
```

---

## 9. Delta Calculator (`delta_calculator.py`)

Pure data-diffing utility with no DB or embedding logic.

```python
delta = calculate_delta(
    old_data,   # Current DB state: [{_id, data_hash}, ...]
    new_data,   # Latest scrape:    [{_id, data_hash}, ...]
    id_key="_id",
    hash_key="data_hash"
)
# Returns: {"new": [...], "updated": [...], "deleted": [...]}
```

**O(N+M) time:** Single pass using dictionaries — no nested loops.

**Robustness:**
- Records missing `id_key` are silently skipped
- Records missing `hash_key` are treated as empty string → surface as `updated`

**Used by:**
- `orchestrator.py` — delta between all scraped products and the DB
- `sync_products.py` — per-color delta for targeted inserts

---

## 10. Checkpointing (`load_products.py`)

The product loading step downloads images, calls embedding APIs, and inserts rows — an operation that can take hours and may be interrupted.

**Checkpoint file:** `.load_products_checkpoint.json`

Stores the last successfully processed index per JSON file:
```json
{
  "townteam_products.json": 142,
  "lablanca_products.json": "done"
}
```

**Resume behavior:**
- On next run, reading resumes from the checkpointed index
- Completed files are marked `"done"` and skipped entirely
- On interrupt, no work since the last checkpoint is lost

**Failure safeguards:**
- `MAX_CONSECUTIVE_MODAL_FAILURES` (default 20): stops if the embedding API keeps failing (likely quota exhausted)
- `ON CONFLICT (product_url, color) DO NOTHING`: database-level deduplication as a final guard

---

## 11. Sync Pipeline (`sync_products.py`)

Full incremental sync pipeline that keeps the database aligned with the latest scraped data.

```bash
python sync_products.py           # Full sync
python sync_products.py --dry-run # Compute delta only, no writes
```

**Steps:**
1. Fetch all rows from DB (grouped by `product_url` + `color`)
2. Load all JSON files from `Products/`
3. Expand each product into per-color entries with a `data_hash`
4. Run delta calculator
5. Delete rows for `updated` and `deleted` products
6. Insert rows for `new` and `updated` products (checkpointed via `load_products`)

---

## 12. Embeddings (`core/embedding_text.py` + `load_products.py`)

Each product/color combination gets a combined embedding for semantic search.

**Embedding text format (max 45 words, ~77 CLIP tokens):**
```
{gender} {category} by {brand} {title}. color {colors}. material {materials}. {description_tail}
```

**Example:**
```
men's hoodies by Town Team Oversized Cotton Hoodie. color Black, Olive. material cotton.
Heavyweight 100% cotton hoodie. Relaxed fit.
```

**Deliberately excluded from embedding text:** sizes, SKUs, barcodes, prices, availability — these are retrieval filters, not semantic content.

**Embedding pipeline per product/color:**
1. Download product image
2. POST image → Azure CLIP API → image embedding (512-dim)
3. POST text → Azure CLIP API → text embedding (512-dim)
4. Average the two embeddings → final combined embedding
5. Insert into `products` table with both embeddings stored

**Why average image + text:** CLIP embeds images and text in the same space. Averaging makes the product representation robust to both visual and textual queries.

---

## 13. Multi-Store Runner (`egyscraper/run.py`)

Runs many stores concurrently, each isolated in its own subprocess.

```bash
python -m egyscraper.run --all              # All confirmed stores
python -m egyscraper.run --store townteam mitcha lablanca
python -m egyscraper.run --all --parallel 3  # Max 3 concurrent
python -m egyscraper.run --all --verbose     # Stream logs to terminal
```

**Design:**
- **Subprocess per store:** One store crashing or hanging does not affect others
- **Threading + semaphore:** Enforces the concurrency limit
- **Per-store log files:** Written to `data/<slug>/scrapy.log` (keeps terminal clean)
- **Live terminal summary:** One line per store, final table with counts and elapsed time

---

## 14. Store Registry (`stores/`)

### `shopify_stores.py`
Registry of ~20 confirmed Shopify stores with slugs, base URLs, and currencies.

### `classification.py`
Planning document mapping all 40 target stores to platform, extraction method, implementation status, and confidence level.

**Extraction priority order (fastest/most reliable first):**
1. Public JSON API (e.g., Shopify `/products.json`)
2. Mobile API
3. GraphQL
4. Embedded JSON (hydration payload in `<script>` tags)
5. JSON-LD (`schema.org` in HTML)
6. Server-rendered HTML (CSS selectors)
7. Browser automation / Playwright (last resort)

---

## 15. Scrapy Settings (`egyscraper/settings.py`)

All operational knobs are environment-configurable.

**Politeness:**
- `CONCURRENT_REQUESTS = 16`, `CONCURRENT_REQUESTS_PER_DOMAIN = 4`
- `DOWNLOAD_DELAY = 0.5s`
- `AUTOTHROTTLE_ENABLED = true` — adapts delay to server response times
- `ROBOTSTXT_OBEY = true`

**Resilience:**
- `RETRY_TIMES = 3`
- Retried HTTP codes: `403, 429, 500, 502, 503, 504, 522, 524, 408`
- HTTP cache: optional, 24-hour expiry (useful for development)

**Bot avoidance:**
- User agent rotation: coherent Chrome browser profiles (UA string + matching `sec-ch-ua` headers)
- Proxy hook: documented and wired in `middlewares.py`, disabled by default (enable via `PROXY_URL` env var)

---

## 16. Database (PostgreSQL on Azure)

**Connection:** Azure Database for PostgreSQL via `psycopg2`, credentials in `.env`.

**Key tables:**

```sql
-- Main products table
CREATE TABLE public.products (
    id           UUID PRIMARY KEY,
    name         TEXT,
    price        FLOAT,
    vendor       TEXT,
    category     TEXT,
    product_url  TEXT,
    color        TEXT,
    image_url    TEXT,
    img_emb      VECTOR(512),   -- Image embedding
    txt_emb      VECTOR(512),   -- Text embedding
    data_hash    TEXT,
    UNIQUE(product_url, color)
);

-- Product images
CREATE TABLE public.product_images (
    id           UUID PRIMARY KEY,
    product_url  TEXT,
    image_url    TEXT,
    UNIQUE(product_url, image_url)
);
```

**Composite key `(product_url, color)`:** One DB row per product/color combination. This granularity allows the delta calculator to detect color-level price and availability changes independently.

---

## 17. Key Design Principles

**Determinism:** Product IDs, variant IDs, content hashes, and embedding texts are all deterministic. The same product always produces the same identifiers across separate crawl runs.

**Decimal money:** All prices use Python's `Decimal` type (quantized to 2 places). Serialized via `simplejson` with `use_decimal=True` so they appear as true JSON numbers (not strings). This avoids the binary float artifacts that would corrupt price comparisons and change detection hashes.

**Fault isolation:** Subprocess per store, logged and skipped bad items, empty-run protection on export files. Any component can fail without cascading.

**Single responsibility per pipeline stage:** Each pipeline stage does one thing. Scope filtering happens in exactly one place (`ScopeFilterPipeline`). Normalization happens before scope checks. Deduplication happens before scope checks.

**Pluggable extraction:** The schema, pipeline, normalization, and DB loading layers are completely decoupled from the extraction method. A Shopify spider, a JSON-LD spider, a Selenium spider, and a Beautiful Soup script all produce the same `ProductItem` shape and flow through the same pipeline.

---

## Technology Stack Summary

| Component | Technology |
|---|---|
| Web scraping framework | Scrapy 2.13+ |
| Browser automation (fallback) | Selenium / scrapy-playwright |
| HTML parsing (utility) | Beautiful Soup |
| Database | PostgreSQL (Azure) via psycopg2 |
| Embeddings model | CLIP (hosted on Azure App Service) |
| Decimal serialization | simplejson |
| Domain extraction | tldextract |
| Configuration | python-dotenv |
| Testing | pytest |
| Language | Python 3.10+ |
