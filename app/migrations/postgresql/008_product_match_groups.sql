CREATE TABLE IF NOT EXISTS product_match_groups (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, identifier_type, normalized_value)
);

CREATE TABLE IF NOT EXISTS product_match_members (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES product_match_groups(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_id, product_id)
);

CREATE INDEX IF NOT EXISTS idx_product_match_members_product
ON product_match_members(product_id, group_id);
