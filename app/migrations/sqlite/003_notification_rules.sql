CREATE TABLE IF NOT EXISTS notification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    site_id INTEGER,
    name TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'webhook',
    target_url TEXT NOT NULL,
    event_types_json TEXT NOT NULL DEFAULT '["product_new"]',
    min_severity TEXT NOT NULL DEFAULT 'normal',
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_notification_rules_user_enabled
ON notification_rules(user_id, enabled, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_rules_site
ON notification_rules(site_id);
