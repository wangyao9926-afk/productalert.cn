CREATE TABLE IF NOT EXISTS notification_rules (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    site_id BIGINT REFERENCES sites(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'webhook',
    target_url TEXT NOT NULL,
    event_types JSONB NOT NULL DEFAULT '["product_new"]'::jsonb,
    min_severity TEXT NOT NULL DEFAULT 'normal',
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notification_rules_user_enabled
ON notification_rules(user_id, enabled, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_rules_site
ON notification_rules(site_id);
