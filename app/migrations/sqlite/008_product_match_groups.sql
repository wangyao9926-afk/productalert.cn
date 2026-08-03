CREATE TABLE IF NOT EXISTS product_match_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    identifier_type TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, identifier_type, normalized_value)
);

CREATE TABLE IF NOT EXISTS product_match_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(group_id) REFERENCES product_match_groups(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(group_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_product_match_members_product
ON product_match_members(product_id, group_id);
