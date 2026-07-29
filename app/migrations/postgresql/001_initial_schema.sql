CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS sites (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1 REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
    webhook_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    category TEXT,
    priority INTEGER NOT NULL DEFAULT 2,
    notes TEXT,
    notification_events JSONB NOT NULL DEFAULT '["product_new"]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMPTZ,
    last_status TEXT,
    UNIQUE(user_id, url)
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS monitor_sources (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL DEFAULT 'homepage',
    url TEXT NOT NULL,
    selector TEXT,
    include_keywords TEXT,
    exclude_keywords TEXT,
    scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    baseline_completed_at TIMESTAMPTZ,
    product_baseline_completed_at TIMESTAMPTZ,
    failure_count INTEGER NOT NULL DEFAULT 0,
    next_scan_after TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMPTZ,
    last_status TEXT,
    UNIQUE(site_id, source_type, url)
);

CREATE TABLE IF NOT EXISTS known_urls (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES monitor_sources(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title_hint TEXT,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, url)
);

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES monitor_sources(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    image_url TEXT,
    price TEXT,
    price_amount NUMERIC(14, 4),
    currency TEXT,
    compare_at_price NUMERIC(14, 4),
    availability TEXT,
    variant_count INTEGER,
    item_type TEXT NOT NULL DEFAULT 'unknown',
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    discovery_status TEXT NOT NULL DEFAULT 'new',
    extraction_source TEXT NOT NULL DEFAULT 'unknown',
    confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    field_confidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    features JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_hash TEXT NOT NULL,
    raw_text TEXT,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(site_id, url)
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES monitor_sources(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    candidates_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id BIGSERIAL PRIMARY KEY,
    parent_job_id BIGINT REFERENCES scan_jobs(id) ON DELETE SET NULL,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES monitor_sources(id) ON DELETE SET NULL,
    job_type TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'queued',
    queued_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    candidates_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    result JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS source_snapshots (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT NOT NULL REFERENCES monitor_sources(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    selector TEXT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_hash TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    extracted_text TEXT
);

CREATE TABLE IF NOT EXISTS change_events (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES monitor_sources(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(id) ON DELETE SET NULL,
    snapshot_before_id BIGINT REFERENCES source_snapshots(id) ON DELETE SET NULL,
    snapshot_after_id BIGINT NOT NULL REFERENCES source_snapshots(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL DEFAULT 'text_change',
    severity TEXT NOT NULL DEFAULT 'normal',
    summary TEXT,
    diff JSONB NOT NULL DEFAULT '[]'::jsonb,
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES products(id) ON DELETE SET NULL,
    event_id BIGINT REFERENCES change_events(id) ON DELETE SET NULL,
    event_type TEXT,
    channel TEXT NOT NULL DEFAULT 'webhook',
    target_url TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    site_id BIGINT REFERENCES sites(id) ON DELETE SET NULL,
    source_id BIGINT REFERENCES monitor_sources(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT,
    action TEXT NOT NULL,
    summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_products_detected_at
ON products(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_products_site_review
ON products(site_id, review_status, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_sources_site_id
ON monitor_sources(site_id);

CREATE INDEX IF NOT EXISTS idx_known_urls_source_id
ON known_urls(source_id);

CREATE INDEX IF NOT EXISTS idx_scan_logs_started_at
ON scan_logs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_queued
ON scan_jobs(status, queued_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_site_id
ON scan_jobs(site_id, queued_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_source_id
ON source_snapshots(source_id, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_change_events_created_at
ON change_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_status_next
ON notification_outbox(status, next_attempt_at ASC, id ASC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_outbox_event_target
ON notification_outbox(event_id, target_url)
WHERE event_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_outbox_product_target_legacy
ON notification_outbox(product_id, target_url)
WHERE product_id IS NOT NULL AND event_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_created
ON audit_logs(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_site_created
ON audit_logs(site_id, created_at DESC);
