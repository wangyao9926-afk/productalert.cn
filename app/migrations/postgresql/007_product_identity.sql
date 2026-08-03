CREATE TABLE IF NOT EXISTS product_identifiers (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, identifier_type, normalized_value)
);

CREATE INDEX IF NOT EXISTS idx_product_identifiers_lookup
ON product_identifiers(identifier_type, normalized_value, product_id);
