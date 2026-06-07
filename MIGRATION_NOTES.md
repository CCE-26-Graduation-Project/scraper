# Migration notes

This release implements every Critical and High Priority finding from the
engineering review, plus a runtime fix surfaced by a real crawl on Scrapy 2.16.
It changes the output schema and a few internals. Read this before upgrading a
database or a downstream consumer.

## Runtime fix (why an earlier run scraped zero items)

A real run of `scrapy crawl shopify -a store=townteam` finished with zero items
and nothing scheduled. Root cause: Scrapy 2.13 replaced the synchronous
`start_requests()` seed method with an async `start()` coroutine, and the
default `start()` only reads `start_urls`. There is no automatic bridge from
`start_requests()`, so a spider that defined only `start_requests` produced no
requests on Scrapy 2.13 and later.

Fix: the spider now defines both an async `start()` (used by Scrapy 2.13+) and
`start_requests()` (used by older Scrapy), each delegating to one shared
generator. Verified end to end against a local Shopify style server: one item
in, full schema out. The requirements floor is now `scrapy>=2.13`.

Related fix: `allowed_domains` now uses the registrable domain (for example
`iravin.com` for `shop.iravin.com`), so redirects between apex, `www` and
subdomains are not dropped as offsite. The port is stripped, which also fixes
local testing.

## Schema changes

New product level fields: `brand_normalized`, `sku`, `barcode`, `gtin`,
`variants`, `content_hash`, `source_updated_at`, `first_seen`, `last_seen`.

New `variants` array. Each product now carries its variants instead of
collapsing them. A variant has: `variant_id`, `platform_variant_id`, `sku`,
`barcode`, `size`, `color`, `price`, `original_price`, `currency`, `available`,
`inventory_quantity`. The product level `price` is still present as the lowest
variant price (a roll up, not a collapse); per size price and stock now live on
each variant.

Money is now `Decimal`. `price` and `original_price`, at both product and
variant level, are parsed to two place Decimals and serialized as true JSON
numbers via simplejson (no float anywhere in the path). In JSON output a price
reads as `799.00`. This is a representation change for anyone who parsed prices
as floats before; parse them as decimals or fixed point now.

Identifiers. Product level `sku`, `barcode` and `gtin` are filled only when
unambiguous (a single variant); otherwise they are null and the truth is on the
variants. A 13, 14, 12 or 8 digit barcode is also exposed as `gtin`.

## Deterministic id changes

`product_id` now follows an explicit hierarchy: platform product id, then
product handle, then canonical url, hashed with the merchant. Variant level
codes are intentionally not used for the product id because a product has many.

New `variant_id`: hashed from the product id plus the strongest variant code
(barcode, then gtin, then sku, then platform variant id, then size and colour,
then a positional index). This is what cross store matching and the database
key on.

Note: because the product id hierarchy changed (handle is now a tier), ids for
products that previously fell back to url but have a handle will differ from the
prior release. Treat this release as a fresh id baseline; re crawl to repopulate.

## Normalization changes

Category, gender and colours now understand Arabic as well as English, and the
design takes language keyed synonym lists so more languages are additive. A
`shoes` category was added, and `tank top` and `crop top` now classify. Colours
normalize to a canonical English token (Arabic and English collapse together),
which improves faceting and text retrieval.

## Pipeline and settings changes

New `ChangeTrackingPipeline` stamps `content_hash`, `first_seen` and
`last_seen`. Pipelines and middlewares were migrated to the Scrapy 2.13 calling
convention (no required `spider` argument; context comes from `self.crawler`),
which removes the per request deprecation warnings.

New settings: `EXPORT_JSON_ARRAY` (default true; turn off for very large
catalogs to skip the array file) and `EXPORT_FLUSH_EVERY` (default 200; batches
JSONL flushes so writes are not one syscall per item).

New dependencies: `simplejson` (Decimal serialization) and `tldextract`
(registrable domain; it already ships with Scrapy).

## Incremental crawl foundation (not yet scheduled)

New `egyscraper/core/change_tracking.py` provides `content_hash`,
`detect_changes`, and a `CrawlState` JSON store with a per store high water
mark. The database gains a `crawl_state` table and `content_hash`, `first_seen`
and `last_seen` columns. Scheduling and delta requests are intentionally left
for a later phase; this is the data layer they will use.

## CLIP integration validation

The embedding text builder was reviewed to confirm variant data does not
pollute embeddings. Sizes, skus, barcodes, variant ids, per variant prices and
stock are excluded by design; only gender, category, brand, title, the
normalized colour set, material and a trimmed description go into the 45 word,
under 77 token string. Real output from the actual builder:

Hoodie
* embedding text: men's hoodies. by Town Team. Oversized Cotton Hoodie. color
  Black, Olive. material cotton. Heavyweight 100% cotton hoodie. Relaxed fit.
* stored metadata (filters, not embedded): category hoodies, gender men, price
  799.00, original 999.00, colors Black and Olive, sizes S and M, three
  variants each with sku, size, price and availability.

Dress
* embedding text: women's dresses. by La Blanca. Floral Summer Maxi Dress.
  color Red. material viscose. Lightweight viscose maxi dress with a floral
  print.
* stored metadata: category dresses, gender women, price 1250.00, original
  1500.00, sku LB-DRESS-OS-RED, barcode and gtin 6224000999013.

Athletic shoes
* embedding text: unisex shoes. by Magma Sportswear. Air Runner Athletic Shoes.
  color White, Black. Lightweight running sneakers with a breathable mesh
  upper.
* stored metadata: category shoes, gender unisex, price 1899.00, sizes 41, 42,
  43 (kept out of the embedding text), three variants.

Why this representation is optimal: it front loads the attributes shoppers
actually type ("women's red maxi dress", "unisex running shoes") so the text
embedding aligns with both the product image and natural language queries,
while keeping the tiny token budget free of size lists and identifiers that
would only add noise and pull unrelated products together. Sizes and prices
remain fully queryable as structured filters, which is where they belong.
