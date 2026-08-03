CREATE TABLE IF NOT EXISTS product_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    external_id TEXT NOT NULL,
    sku TEXT,
    title TEXT,
    option_values TEXT NOT NULL DEFAULT '',
    price TEXT,
    price_amount REAL,
    compare_at_price REAL,
    availability TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_product_variants_product
ON product_variants(product_id, last_seen_at DESC);
