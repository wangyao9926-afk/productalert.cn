CREATE TABLE IF NOT EXISTS product_variants (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    sku TEXT,
    title TEXT,
    option_values TEXT NOT NULL DEFAULT '',
    price TEXT,
    price_amount NUMERIC(14, 4),
    compare_at_price NUMERIC(14, 4),
    availability TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_product_variants_product
ON product_variants(product_id, last_seen_at DESC);
