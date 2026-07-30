ALTER TABLE product_variants ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_product_variants_active
ON product_variants(product_id, is_active, last_seen_at DESC);
