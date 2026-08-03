CREATE TABLE IF NOT EXISTS event_suppression_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    change_type TEXT NOT NULL,
    reason TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE CASCADE,
    UNIQUE(source_id, change_type)
);

CREATE INDEX IF NOT EXISTS idx_event_suppression_rules_site
ON event_suppression_rules(site_id, enabled, created_at DESC);
