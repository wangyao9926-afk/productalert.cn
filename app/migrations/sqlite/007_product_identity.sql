CREATE TABLE IF NOT EXISTS product_identifiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    raw_value TEXT NOT NULL,
    provenance TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, identifier_type, normalized_value)
);

CREATE INDEX IF NOT EXISTS idx_product_identifiers_lookup
ON product_identifiers(identifier_type, normalized_value, product_id);
