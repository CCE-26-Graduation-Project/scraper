# Engineering Review: egyscraper

Production readiness review of the data acquisition layer before it becomes the
foundation for multimodal retrieval (CLIP, PostgreSQL plus pgvector, price
comparison, similar product discovery, cross store matching).

Reviewed: the full `egyscraper` codebase, the test suite, the standardized
schema, and the planned data flow into the retrieval system. The suite was
expanded from 61 to 100 tests during this review (all passing) to ground the
findings and close coverage gaps. Two concrete artifacts were added:
`egyscraper/core/embedding_text.py` (the CLIP text builder) and `db/schema.sql`
(the PostgreSQL plus pgvector design).

Overall verdict: the architecture is sound and the Shopify pattern is a strong
primary extraction method. The framework is not yet ready to feed the matching
layer, because at the moment of acquisition it discards the two things the
matching and comparison goals depend on most: per variant price and stock, and
stable product identifiers. Those are the headline fixes. Everything else is
incremental hardening.

---

## Task 1 — Codebase audit

### Critical

C1. Stable cross store identifiers are discarded at the source.
Explanation: cross store matching and price comparison want an exact key
(SKU, barcode or GTIN, manufacturer part number) before falling back to fuzzy
CLIP similarity. Shopify exposes a `sku` on every variant, and many stores
expose a barcode, but the mapper drops both. Once a crawl runs without
capturing them, the only way to recover is to re crawl. This directly weakens
two stated end goals.
Fix: capture variant `sku` and `barcode` in the mapper, add `sku`, `gtin`,
`mpn` to the schema, and key cross store matching on them when present.

C2. Variant level price and stock are collapsed away.
Explanation: the mapper emits a single price (the lowest variant) and a single
`availability` boolean (any variant available). For a price comparison and "is
my size in stock" product, the per size price and per size availability are the
data. They are lost at acquisition and unrecoverable without re crawl.
Fix: emit a `variants` array (size, color, sku, price, available) alongside the
summary fields, and persist it to the `product_variants` table.

### High Priority

H1. Money flows as a float end to end.
Explanation: prices are parsed and stored as Python floats. Float is the wrong
representation for money: 799.0 is fine, but aggregation, discount math and
equality comparisons across stores accumulate rounding error. For a comparison
engine this is a correctness risk.
Fix: keep parsing tolerant, but store as `NUMERIC(12,2)` in PostgreSQL (done in
`db/schema.sql`) and treat prices as decimals, never compare as floats.

H2. Category and gender are English only.
Explanation: `normalize.normalize_category` and `normalize_gender` use English
keyword maps. A large share of Egyptian store catalogs label products in
Arabic (and franco Arabic), so those records end with empty `category` and
`gender`. That degrades faceted retrieval and the metadata that the embedding
text relies on. Confirmed by `tests/test_edge_cases.py::test_arabic_category_currently_unclassified`.
Fix: add Arabic keyword maps to the normalizers, and consider a lightweight
transliteration pass for franco Arabic.

H3. No true incremental crawl.
Explanation: every run refetches the full catalog and truncates the JSONL on
open. Deterministic ids make database upsert correct, but the network cost of
refetching tens of thousands of products on every update cycle does not scale
with "frequent updates". The Shopify payload carries `updated_at`, which is
unused.
Fix: support an updated since mode (skip products whose `updated_at` predates
the last successful crawl), and record a per store high water mark.

H4. Offsite and redirect handling can silently drop requests.
Explanation: `allowed_domains` is set to the exact netloc. A store whose
`/products.json` redirects between `www` and apex, or to a regional host, can
have follow up requests filtered by the offsite middleware, truncating the
catalog with no error.
Fix: allow the registrable domain (strip a leading `www.`) or disable offsite
filtering for these JSON crawls, and log redirects.

H5. Exporter performance and duplicate storage.
Explanation: the JSONL exporter calls `flush()` on every item, which is one
write syscall per product (hundreds of thousands of them), and it always
assembles a full `products.json` array in addition to the JSONL. The array is
redundant for the database loader and doubles disk writes.
Fix: flush periodically (for example every N records) rather than per item, and
make the JSON array opt in. JSONL is the canonical feed for ingestion.

### Medium Priority

M1. `ProductItem` is effectively unused; the pipeline carries a dual code path.
Spiders yield plain dicts, so the Scrapy `Item` class and the item branch of
`_as_dict` are dead weight. Pick one representation (dict is simpler) and drop
the other, or standardize spiders on the item.

M2. The multi store runner has no per store timeout.
`run.py` isolates store failures by subprocess, but a hung store stalls the
whole sequential run. Add `subprocess.run(..., timeout=...)` and treat timeouts
as a failed store. Sequential execution is fine for politeness; document it.

M3. Loose data quality gates in validation.
A product priced at 0 passes validation, and products with empty descriptions
pass with a weak embedding text. Consider rejecting or flagging zero prices and
recording a quality score so the embedding step can skip or down weight thin
records.

M4. Category keyword gaps.
"tank top" and "crop top" do not classify, and "polo" maps to t shirts (which is
debatable). Pinned in `tests/test_edge_cases.py`. Expand the keyword rules.

M5. `CloseSpider` raised from `__init__`.
`CloseSpider` is intended for callbacks; raising it during construction works
but is improper. Use `ValueError` for bad arguments.

M6. The fashion gate is permissive on no signal.
`is_fashion` returns True when there is no signal, which is right for pure
clothing stores but risky for marketplaces (Task 5 stores Jumia, Noon, Amazon).
Before those land, tighten the gate to require a positive fashion signal on
marketplace spiders.

### Low Priority

L1. `brand` duplicates `vendor` for Shopify. Harmless, but add a normalized
brand (lowercased, trimmed) for matching rather than duplicating raw text.

L2. Structured logging is only partially met. Settings define a readable log
format but not machine parseable JSON logs. Add an optional JSON log formatter
if log ingestion is planned.

L3. `scraped_at` is set inside the mapper. Centralize it in a pipeline so every
future spider gets it for free without remembering to set it.

L4. `core/api.py` and `core/jsonld.py` had no consumer yet. They are
forward looking scaffolding for non Shopify stores; now covered by tests, but
keep them honest by landing them with their first real spider.

---

## Task 2 — Testing review

Before this review: 61 tests covering ids, normalizers, schema, the Shopify
mapper, and pipelines. Strong on pure logic, but nothing on the JSON LD and API
helpers, the embedding text, the exporter, the spider's own request and
pagination logic, or non English and boundary inputs.

Added during this review (now 100 tests, all passing):

* `tests/test_jsonld.py` (7): block extraction, `@graph` and list typed nodes,
  malformed block resilience, absent product.
* `tests/test_api.py` (6): GET versus POST body encoding, header merging,
  GraphQL body shape, JSON parsing failure path.
* `tests/test_embedding_text.py` (6): attribute presence, token budget,
  title survival under a long description, no dangling labels, determinism.
* `tests/test_edge_cases.py` (10): no variant and no image products, comma
  string tags, missing handle, discarded compare at price, zero and Arabic
  currency prices, and two pinned known limitations (Arabic category, tank top).
* `tests/test_exporter.py` (4): JSONL write and count, JSON array round trip,
  unicode preservation, truncate on reopen.
* `tests/test_spider.py` (7): argument validation, start request target,
  pagination on a full page, stop on a short page, fashion filtering, non JSON
  response handling.

Coverage estimate: the pure logic layer (ids, normalize, schema, shopify
mapper, embedding text, exporters, pipelines) is now near fully covered. The
spider's parsing and pagination are covered with a fake response. The only
uncovered surface is genuine network behaviour against live stores, which
belongs in a small integration test run on demand, not in the unit suite.

Still recommended before heavy production use: one opt in integration test that
hits a single real Shopify store and asserts the schema on the first page, run
manually rather than in CI to avoid hammering a live site.

---

## Task 3 — Schema review

The current 23 field schema is a solid base for text retrieval and storage. It
is not yet sufficient for the full goal. Assessment by purpose:

* CLIP text embedding: sufficient once an explicit `embedding_text` field is
  stored (see Task 4). Today the text is implicit.
* Visual similarity: needs image structure with stable per image references so
  that multiple image embeddings per product are possible. A flat `image_urls`
  list is workable but better modelled as image rows.
* Text retrieval and comparison: weakened by the missing identifiers (C1) and
  variant detail (C2).
* PostgreSQL and pgvector storage: fine as a row, but money must be numeric.

Missing fields: `sku`, `gtin`, `mpn`, `variants` (per size price and stock),
`embedding_text`, `brand_normalized`, `source_updated_at`.

Redundant fields: `brand` duplicates `vendor` for Shopify; keep both but add the
normalized form.

Fields to normalize differently: `price` and `original_price` as decimals, not
floats; `category` and `gender` with Arabic support.

Revised schema (additions and changes to the existing record):

| Field | Change | Reason |
|---|---|---|
| `sku` | add (string, nullable) | exact cross store key |
| `gtin` | add (string, nullable) | barcode / global identity |
| `mpn` | add (string, nullable) | manufacturer part for matching |
| `variants` | add (array of objects) | per size price and stock |
| `embedding_text` | add (string) | reproducible CLIP input |
| `brand_normalized` | add (string) | matching and faceting |
| `source_updated_at` | add (timestamp) | incremental crawl, freshness |
| `price`, `original_price` | numeric, not float | money correctness |
| `category`, `gender` | Arabic aware | Egyptian catalog coverage |

---

## Task 4 — CLIP data design

CLIP aligns images and text in one shared 512 dimension space (for ViT-B/32).
"Search by image" compares an image embedding to stored image embeddings.
"Search by text" embeds the query text and compares it to the same image
embeddings (cross modal), and optionally to stored text embeddings (text to
text). The critical constraint: the CLIP text encoder truncates at 77 tokens
(roughly 50 to 60 words). Anything beyond is dropped, so the embedding text must
be short and front loaded with the most discriminative attributes.

Per field decision (embedded means it goes into the CLIP text string; indexed
means a filter or sort column; stored means kept but not embedded):

| Field | Embedded | Indexed | Stored | Note |
|---|---|---|---|---|
| title | yes | no | yes | primary signal |
| description | yes (trimmed) | no | yes | append only if budget remains |
| category | yes (light) | yes | yes | also a hard filter |
| subcategory | no | yes | yes | filter |
| gender | yes (light) | yes | yes | matches how users phrase queries |
| brand / vendor | yes (light) | yes | yes | brand aware retrieval |
| colors | yes | yes (GIN) | yes | strong visual + text signal |
| material | yes | yes (GIN) | yes | discriminative for clothing |
| sizes | no | yes | yes | filter only, not semantic |
| price, original_price | no | yes | yes | sort and filter, never embedded |
| availability | no | yes | yes | filter |
| rating, review_count | no | yes | yes | ranking signal |
| image_urls, main_image | image side | no | yes | source of image embeddings |
| attributes | selective | selective | yes | promote fit/season into text |
| product_url, source, product_id, scraped_at | no | yes | yes | never embedded |
| embedding_text | n/a | no | yes | the stored artifact |

1. Recommended text representation: the compact structured string produced by
`build_embedding_text`. Fixed order (gender, category, brand, title, colors,
material, then a trimmed description tail), deduped, capped at 45 words to stay
safely under 77 tokens, deterministic so embeddings are reproducible.

2. Recommended metadata representation: everything not embedded becomes a
filterable column (price, gender, category, availability) or a GIN indexed
array (colors, sizes, materials), with the long tail in JSONB `attributes`.

3. Recommended PostgreSQL schema: see `db/schema.sql` and Task 8.

4. Example embedding text generated from a real mapped product (the hoodie
fixture, produced by the actual builder):

> men's hoodies. by Town Team. Oversized Cotton Hoodie. color Black, Olive.
> material cotton. Heavyweight 100% cotton hoodie. Relaxed fit.

Approach comparison:

* Approach A, title only. Cheapest, but a query like "men's black cotton hoodie"
  has nothing to align to beyond the title text. Weak recall on attribute style
  queries, which dominate fashion search.
* Approach B, title plus full description. Richer, but descriptions are often
  marketing boilerplate, frequently empty on Shopify, and long ones push the
  title past the 77 token limit, dropping the most discriminative tokens.
  Inconsistent quality across stores.
* Approach C, structured title plus category, gender, color, material, then a
  trimmed description. Front loads controlled vocabulary attributes that match
  how shoppers phrase queries, stays within budget, and is consistent across
  stores regardless of description quality.

Recommendation: Approach C. It produces the most reliable retrieval because it
guarantees the discriminative attributes are always present and never truncated,
which matters more for cross modal alignment than raw description length.

---

## Task 5 — Store classification report

Platform labels are best assessment from the target list and the prototype's
verified inputs. Anything not marked high confidence must be checked against the
live site (open `<domain>/products.json`) before a spider is trusted. Sorted
easiest to hardest.

| # | Store | Domain | Platform | Strategy | Confidence | Difficulty | Maintenance |
|---|---|---|---|---|---|---|---|
| 1 | Town Team | townteam.com | Shopify | JSON endpoint | High | Easy | Low |
| 2 | La Blanca | lablancaegypt.com | Shopify | JSON endpoint | High | Easy | Low |
| 3 | Iravin | shop.iravin.com | Shopify | JSON endpoint | High | Easy | Low |
| 4 | Sigma Fit | sigmafiteg.com | Shopify | JSON endpoint | High | Easy | Low |
| 5 | Way Up Sports | wayupsports.com | Shopify | JSON endpoint | High | Easy | Low |
| 6 | Mitcha | mitcha.com | Shopify | JSON endpoint | High | Easy | Low |
| 7 | Basic Look | basiclook.com | Shopify | JSON endpoint | High | Easy | Low |
| 8 | Gorilla Outfit | gorillaoutfit.com | Shopify | JSON endpoint | High | Easy | Low |
| 9 | Intersport EG | intersport.com.eg | Shopify | JSON endpoint | Medium | Easy | Low |
| 10 | Carina Wear | carinawear.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 11 | Tomato Store | tomatostore.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 12 | Magma Sportswear | magmasportswear.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 13 | Pink Shop | pinkshopeg.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 14 | Tie House | tie-house.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 15 | Your Emma | youremma.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 16 | Izzy Apparel | izzyapparel.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 17 | Mobaco | mobaco.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 18 | Lavito Scarf | lavitoscarf.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 19 | Andora | andoraeg.com | Shopify | JSON endpoint | Medium | Easy | Low |
| 20 | American Eagle EG | americaneagle.com.eg | Shopify | JSON endpoint | Low | Easy | Low |
| 21 | Alo Yoga EG | aloyoga.com/en-eg | Shopify Plus | JSON endpoint | Medium | Medium | Medium |
| 22 | Accessorize | accessorize.com | Shopify | JSON endpoint | Low | Medium | Medium |
| 23 | DeFacto EG | defacto.com.eg | Custom / Next.js | JSON LD or embedded JSON | Low | Medium | Medium |
| 24 | LC Waikiki EG | lcwaikiki.eg | Custom | JSON LD or embedded JSON | Low | Medium | Medium |
| 25 | Decathlon EG | decathlon.eg | Custom | REST API | Low | Medium | Medium |
| 26 | Mango EG | shop.mango.com/eg | Custom | embedded JSON | Low | Medium | High |
| 27 | Max Fashion EG | maxfashion.com/eg | Custom (Landmark) | REST API | Low | Medium | High |
| 28 | Adidas EG | adidas.com.eg | Salesforce Commerce | embedded JSON or API | Medium | Hard | High |
| 29 | New Balance EG | newbalance.com.eg | Salesforce Commerce | embedded JSON or API | Low | Hard | High |
| 30 | Lacoste EG | lacoste.com.eg | Salesforce Commerce | embedded JSON or API | Low | Hard | High |
| 31 | Foot Locker EG | footlocker.com.eg | Custom | embedded JSON or API | Low | Hard | High |
| 32 | H&M EG | eg.hm.com | Custom | REST API | Medium | Hard | High |
| 33 | Zara EG | zara.com/eg | Inditex custom | REST API | Medium | Hard | High |
| 34 | Pull and Bear EG | pullandbear.com/eg | Inditex custom | REST API | Medium | Hard | High |
| 35 | Nike EG | nike.com/eg | Nike custom | REST API | Medium | Very Hard | Very High |
| 36 | Jumia EG | jumia.com.eg | Custom marketplace | embedded JSON or HTML | Medium | Hard | High |
| 37 | Noon Egypt | noon.com/egypt-en | Custom marketplace | mobile or REST API | Medium | Hard | High |
| 38 | Dabchy | dabchy.com.eg | Custom marketplace | API or HTML | Low | Hard | High |
| 39 | Amazon EG | amazon.com.eg | Amazon | mobile API or HTML | Medium | Very Hard | Very High |

---

## Task 6 — Implementation roadmap

Principle: maximise coverage with the least new code and the lowest maintenance,
reuse one pattern across many stores, and defer anti bot heavy sites until the
catalog already has value.

Phase 3, finish Shopify and add one reusable pattern.
* Verify and onboard stores 9 to 22. Each is a registry entry plus a one minute
  `/products.json` check, no new spider code. This is the fastest coverage gain
  on the board.
* Apply the Shopify hardening from Task 7 (variant and sku capture, locale path
  handling, disabled endpoint detection, pagination stop conditions).
* Build one generic JSON LD spider and point it at the structured custom stores
  (DeFacto, LC Waikiki, Decathlon). JSON LD is a single pattern reused across
  many sites, so this multiplies coverage without per store code.
Justification: highest coverage per unit of effort, lowest maintenance, and it
delivers the second reusable extraction pattern the project needs.

Phase 4, marketplaces and the Salesforce Commerce pattern.
* Jumia and Noon: highest product volume on the list, but each needs a dedicated
  spider with strict fashion category filtering. Worth the cost for the volume.
* Salesforce Commerce Cloud stores (Adidas, New Balance, Lacoste) share one
  platform, so one pattern covers three stores.
Justification: high value and pattern reuse, while still deferring the worst
anti bot sites.

Phase 5, hard vendor APIs and Amazon last.
* Inditex (Zara, Pull and Bear), H&M, Nike: vendor specific APIs with aggressive
  rate limits, likely needing rotating proxies.
* Amazon last: very hard anti bot, highest maintenance, only justified once the
  catalog and the proxy budget exist.
Justification: tackle the highest cost, highest maintenance targets only after
the cheaper coverage is banked and the system has proven value.

---

## Task 7 — Shopify implementation review

Pagination limitations: the spider pages by `page` until a short page or the
`MAX_PAGES` safety cap. The public `products.json` endpoint historically limits
how deep page based paging goes on some stores, so very large catalogs can be
truncated silently. Recommend cross checking the catalog count against
`/products.json` totals or the products sitemap, and logging when `MAX_PAGES` is
hit.

Catalog completeness risks: `products.json` reflects products published to the
online store sales channel. Unpublished, draft, or channel restricted products
do not appear, and some Shopify Plus stores disable the endpoint entirely. Build
a detector: if the endpoint returns non JSON or 404, fall back to the products
sitemap or `collections.json`, and flag the store.

Variant handling issues: variants are collapsed to a single min price and an any
available boolean (audit C2). Per size price, per size stock, and per variant
sku are lost. This is the most important Shopify specific fix.

Missing image handling: only `images[].src` is taken, in payload order.
Variant specific images (`variant.featured_image`), alt text, and explicit
position are ignored, so the image to variant mapping needed for "show me this
in blue" is absent.

Missing inventory handling: only the available boolean is captured, never
`inventory_quantity`. Fine for availability, insufficient for stock level
signals.

API limitations: `products.json` carries no ratings, no canonical category
taxonomy, and sometimes empty `body_html`. Ratings and taxonomy must come from
elsewhere or be derived.

Stores likely to break: Shopify Plus stores with the endpoint disabled; stores
on locale prefixed paths such as `aloyoga.com/en-eg` where the bare origin
`products.json` may return the wrong region or nothing; and stores that redirect
between www and apex (audit H4).

Verdict: yes, the Shopify pattern is robust enough to be the primary extraction
method for standard Shopify stores, and it already covers the bulk of the target
list at low maintenance. It is not yet complete: land the variant and sku
capture, locale path handling, disabled endpoint detection, and completeness
cross check before treating Shopify output as production grade.

---

## Task 8 — PostgreSQL and pgvector design

Full DDL is in `db/schema.sql`. Summary:

Tables.
* `products`: one row per deterministic `product_id`, kept narrow for cache
  efficiency. Money as `NUMERIC(12,2)`. Adds `sku`, `gtin`, `brand_normalized`,
  `embedding_text`, `source_updated_at`. Arrays for colors, sizes, materials.
  JSONB `attributes`.
* `product_images`: one row per image with position and an `is_main` flag, so
  each image can carry its own embedding.
* `embeddings`: many per product, with a `modality` enum (text, image, fused), a
  `model` column, and a `vector(512)` column. Keeping vectors out of the
  products row lets retrieval scan a compact table.
* `product_attributes`: normalized key and value rows for the long tail (fit,
  season, neckline) that should be queryable without bloating products.
* `product_variants` (recommended): per size price and stock for true variant
  level comparison.

Indexes.
* HNSW on `embeddings.embedding` with `vector_cosine_ops` (cosine matches CLIP),
  queried with a `modality` filter so each search stays in one space.
* Btree on `products(source, category, gender, price, brand_normalized)`.
* GIN on `attributes`, `colors`, `sizes`.
* Unique on `(source, sku)` where sku is present, for exact identity.

Constraints.
* `price >= 0`, currency is three characters, foreign keys cascade on delete,
  and an embedding consistency check (image embeddings reference an image; text
  and fused do not).

Scaling considerations for hundreds of thousands of products with frequent
updates.
* Upsert on `product_id` so re crawls update rather than duplicate, and only
  regenerate embeddings when title, description or images change, to avoid
  paying GPU cost on price only updates.
* HNSW indexes live in memory; size RAM for the embeddings table and its index,
  not the whole database.
* At low millions of rows, partition `products` and `embeddings` by `source` to
  keep per store maintenance and index rebuilds cheap.
* Tune `ef_search` at query time for the recall versus latency trade off.

---

# Final summary

## 1. Executive summary

The egyscraper architecture is sound and the Shopify extraction pattern is a
strong, low maintenance foundation that already covers most of the target list.
The test suite was expanded to 100 passing tests during this review. The system
is close to ready, but it is not yet ready to feed the matching layer, because
at acquisition time it discards per variant price and stock and the stable
identifiers that cross store matching and price comparison depend on. Fix those,
add Arabic category support, store an explicit embedding text, and move money to
numeric, and the data acquisition layer is production grade for the retrieval
system.

## 2. Critical issues

* C1: stable identifiers (sku, barcode) are dropped at the source, leaving cross
  store matching with no exact key.
* C2: per variant price and stock are collapsed to a single price and a single
  boolean, defeating price comparison and size availability.

## 3. Recommended fixes (in priority order)

1. Capture variant sku, barcode, per size price and stock; add a `variants`
   array and the `product_variants` table (C1, C2).
2. Move money to `NUMERIC` and treat prices as decimals (H1).
3. Add Arabic aware category and gender normalization (H2).
4. Store an explicit `embedding_text` using Approach C (Task 4).
5. Add incremental crawl via `updated_at`, fix offsite and redirect handling,
   and make exporter flushing periodic with the JSON array opt in (H3, H4, H5).
6. Land the Shopify hardening from Task 7 before scaling store count.

## 4. Store classification table

See Task 5. Thirty nine stores: roughly twenty two are Shopify and Easy with Low
maintenance, five are medium custom stores reachable by JSON LD or embedded
JSON, eight are hard vendor or Salesforce Commerce sites, and the marketplaces
plus Amazon are the hardest with the highest maintenance.

## 5. Implementation roadmap

See Task 6. Phase 3 finishes Shopify and adds a reusable JSON LD spider. Phase 4
takes the marketplaces and the shared Salesforce Commerce pattern. Phase 5
handles the hard vendor APIs and Amazon last.

## 6. CLIP integration recommendations

Use Approach C for the text embedding, capped under the 77 token limit and
stored as `embedding_text` for reproducibility (implemented in
`egyscraper/core/embedding_text.py`). Generate a per image embedding for each
product image and a text embedding from the embedding text; optionally store a
fused average. Retrieve image queries against image embeddings, and text queries
against image embeddings (cross modal) and text embeddings (text to text), all
by cosine similarity in the shared space.

## 7. PostgreSQL and pgvector design recommendations

See Task 8 and `db/schema.sql`. Narrow products row with numeric money and
identifier columns, a separate images table, an embeddings table with a modality
enum and a `vector(512)` column indexed by HNSW cosine, a normalized attributes
table, and an optional variants table. Upsert on `product_id`, regenerate
embeddings only on content change, and partition by source as the catalog grows.

## Scope filter layer (added)

`egyscraper/core/scope.py` is the single authoritative scope gate. It runs in
`ScopeFilterPipeline` at priority 410, after category normalisation and before
all downstream stages. Spiders yield everything; no spider contains scope
logic; the pipeline is the only place a product can be rejected for being
out-of-scope, so counts are always accurate.

Keywords are word-boundary matched for Latin script and substring matched for
Arabic. Adding a new language means adding terms to the keyword lists. Adding a
new rejection bucket means appending an entry to `_OUT_OF_SCOPE` in scope.py.

The scope decision is stored in each record's `scope` field and also summarised
in every `crawl_report.json` (`scope_total_discovered`, `scope_accepted`,
`scope_rejected`, `scope_rejection_breakdown`).

The `egyscraper.scope_audit` CLI can dry-run or apply the filter over existing
products.jsonl files to estimate or execute the data migration.
