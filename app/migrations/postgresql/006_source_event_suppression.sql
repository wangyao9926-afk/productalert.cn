CREATE TABLE IF NOT EXISTS event_suppression_rules (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES monitor_sources(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL,
    reason TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, change_type)
);

CREATE INDEX IF NOT EXISTS idx_event_suppression_rules_site
ON event_suppression_rules(site_id, enabled, created_at DESC);
