-- ===========================================================================
-- Intelligent Product Matching System: PostgreSQL + pgvector schema
-- ---------------------------------------------------------------------------
-- Target scale: hundreds of thousands of products, multiple image embeddings
-- per product, frequent re crawls (upsert), CLIP retrieval over text + image.
--
-- Dimension note: vectors are sized for CLIP ViT-B/32 (512). Change vector(512)
-- consistently if you select a different CLIP variant (ViT-L/14 is 768).
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- products: one row per deterministic product_id. Kept deliberately narrow;
-- large or one to many data lives in the side tables below so this hot table
-- stays cache friendly.
-- ---------------------------------------------------------------------------
CREATE TABLE products (
    product_id        CHAR(64) PRIMARY KEY,           -- deterministic SHA256 hex
    source            TEXT        NOT NULL,            -- merchant slug
    vendor            TEXT,
    brand             TEXT,
    brand_normalized  TEXT,                            -- lowercased, for matching
    title             TEXT        NOT NULL,
    description       TEXT,
    category          TEXT,
    subcategory       TEXT,
    gender            TEXT,
    price             NUMERIC(12,2) NOT NULL,          -- money is never a float
    original_price    NUMERIC(12,2),
    currency          CHAR(3)     NOT NULL DEFAULT 'EGP',
    availability      TEXT,
    rating            NUMERIC(3,2),
    review_count      INTEGER,
    main_image        TEXT,
    product_url       TEXT        NOT NULL,
    sku               TEXT,                            -- cross store match key
    gtin              TEXT,                            -- barcode / global id, when present
    barcode           TEXT,                            -- raw barcode as supplied
    mpn               TEXT,                            -- manufacturer part number, when present
    colors            TEXT[]      NOT NULL DEFAULT '{}',
    sizes             TEXT[]      NOT NULL DEFAULT '{}',
    materials         TEXT[]      NOT NULL DEFAULT '{}',
    embedding_text    TEXT,                            -- exact text fed to CLIP
    content_hash      CHAR(64),                        -- change detection fingerprint
    attributes        JSONB       NOT NULL DEFAULT '{}',
    source_updated_at TIMESTAMPTZ,                     -- store's own updated_at
    first_seen        TIMESTAMPTZ,                     -- preserved across crawls
    last_seen         TIMESTAMPTZ,                     -- updated every crawl
    scraped_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT price_non_negative          CHECK (price >= 0),
    CONSTRAINT original_price_non_negative CHECK (original_price IS NULL OR original_price >= 0)
);

CREATE INDEX idx_products_source      ON products (source);
CREATE INDEX idx_products_category    ON products (category);
CREATE INDEX idx_products_gender      ON products (gender);
CREATE INDEX idx_products_price       ON products (price);
CREATE INDEX idx_products_brand_norm  ON products (brand_normalized);
CREATE INDEX idx_products_attributes  ON products USING GIN (attributes);
CREATE INDEX idx_products_colors      ON products USING GIN (colors);
CREATE INDEX idx_products_sizes       ON products USING GIN (sizes);
-- Exact cross store identity when a real product code exists.
CREATE UNIQUE INDEX uq_products_source_sku
    ON products (source, sku) WHERE sku IS NOT NULL;

-- ---------------------------------------------------------------------------
-- product_images: one row per image, ordered. Enables per image embeddings,
-- which the embeddings table references.
-- ---------------------------------------------------------------------------
CREATE TABLE product_images (
    image_id    BIGSERIAL PRIMARY KEY,
    product_id  CHAR(64) NOT NULL REFERENCES products (product_id) ON DELETE CASCADE,
    url         TEXT     NOT NULL,
    position    INTEGER  NOT NULL DEFAULT 0,
    is_main     BOOLEAN  NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_image UNIQUE (product_id, url)
);

CREATE INDEX idx_images_product ON product_images (product_id);

-- ---------------------------------------------------------------------------
-- embeddings: many per product. modality distinguishes a text embedding, a
-- per image embedding, or a fused (averaged) embedding. Keeping vectors out of
-- the products row lets retrieval scan a compact vector table.
-- ---------------------------------------------------------------------------
CREATE TYPE embedding_modality AS ENUM ('text', 'image', 'fused');

CREATE TABLE embeddings (
    embedding_id BIGSERIAL PRIMARY KEY,
    product_id   CHAR(64) NOT NULL REFERENCES products (product_id) ON DELETE CASCADE,
    image_id     BIGINT REFERENCES product_images (image_id) ON DELETE CASCADE,
    modality     embedding_modality NOT NULL,
    model        TEXT     NOT NULL DEFAULT 'clip-vit-base-patch32',
    embedding    vector(512) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- image embeddings reference an image; text and fused do not.
    CONSTRAINT image_ref_consistency CHECK (
        (modality = 'image' AND image_id IS NOT NULL) OR
        (modality <> 'image' AND image_id IS NULL)
    )
);

CREATE INDEX idx_embeddings_product ON embeddings (product_id);

-- Approximate nearest neighbour index. HNSW gives strong recall and fast
-- queries for read heavy retrieval; build per modality so searches stay within
-- one space. Use cosine because CLIP embeddings are compared by cosine.
CREATE INDEX idx_embeddings_hnsw_cosine
    ON embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- Tip: filter by modality in the query (WHERE modality = 'image') so the
-- planner restricts the ANN search to the intended space.

-- ---------------------------------------------------------------------------
-- product_attributes: normalized key/value extras that do not deserve a column
-- (fit, sleeve, neckline, season, pattern, ...). Queryable without bloating the
-- products row or relying solely on the JSONB blob.
-- ---------------------------------------------------------------------------
CREATE TABLE product_attributes (
    product_id CHAR(64) NOT NULL REFERENCES products (product_id) ON DELETE CASCADE,
    name       TEXT     NOT NULL,
    value      TEXT     NOT NULL,
    PRIMARY KEY (product_id, name, value)
);

CREATE INDEX idx_attr_name_value ON product_attributes (name, value);

-- ---------------------------------------------------------------------------
-- product_variants: per variant price, stock and identifiers. This is where
-- the variant level truth lives; the products row carries only roll ups. The
-- variant_id is the deterministic id from core.ids.variant_id.
-- ---------------------------------------------------------------------------
CREATE TABLE product_variants (
    variant_id          CHAR(64) PRIMARY KEY,
    product_id          CHAR(64) NOT NULL REFERENCES products (product_id) ON DELETE CASCADE,
    platform_variant_id TEXT,
    sku                 TEXT,
    barcode             TEXT,
    size                TEXT,
    color               TEXT,
    price               NUMERIC(12,2),
    original_price      NUMERIC(12,2),
    currency            CHAR(3) NOT NULL DEFAULT 'EGP',
    available           BOOLEAN,
    inventory_quantity  INTEGER,
    CONSTRAINT variant_price_non_negative CHECK (price IS NULL OR price >= 0)
);

CREATE INDEX idx_variants_product ON product_variants (product_id);
-- Exact cross store identity at the variant level when a real code exists.
CREATE UNIQUE INDEX uq_variant_source_sku
    ON product_variants (product_id, sku) WHERE sku IS NOT NULL;
CREATE INDEX idx_variants_barcode ON product_variants (barcode) WHERE barcode IS NOT NULL;

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_products_updated
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ---------------------------------------------------------------------------
-- crawl_state: incremental crawl foundation. One row per store records the
-- newest source update seen so a later run can request only what changed. It
-- mirrors the JSON state written by core.change_tracking.CrawlState.
-- ---------------------------------------------------------------------------
CREATE TABLE crawl_state (
    source         TEXT PRIMARY KEY,
    updated_at_max TIMESTAMPTZ,         -- high water mark of source_updated_at
    last_run_at    TIMESTAMPTZ,
    products_seen  INTEGER NOT NULL DEFAULT 0
);

-- ===========================================================================
-- Upsert pattern for re crawls (run by the loader):
--
--   INSERT INTO products (product_id, ..., first_seen, last_seen) VALUES (...)
--   ON CONFLICT (product_id) DO UPDATE SET
--       price = EXCLUDED.price,
--       original_price = EXCLUDED.original_price,
--       availability = EXCLUDED.availability,
--       content_hash = EXCLUDED.content_hash,
--       last_seen = EXCLUDED.last_seen,
--       first_seen = COALESCE(products.first_seen, EXCLUDED.first_seen),
--       scraped_at = EXCLUDED.scraped_at,
--       updated_at = now();
--
-- Regenerate embeddings only when products.content_hash changed, so a price
-- only update does not pay GPU cost. Variants upsert on variant_id.
--
-- Scaling notes:
--   * At low millions of rows, consider partitioning products and embeddings
--     by source (list partitioning) to keep per store maintenance and ANN
--     index rebuilds cheap.
--   * HNSW indexes are memory resident; size RAM for the embeddings table plus
--     index, not the whole DB.
--   * Tune ef_search at query time for the recall/latency trade off.
--   * Keep money in NUMERIC; never compare prices as floats.
-- ===========================================================================
