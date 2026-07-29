CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
    webhook_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    category TEXT,
    priority INTEGER NOT NULL DEFAULT 2,
    notes TEXT,
    notification_events_json TEXT NOT NULL DEFAULT '["product_new"]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    last_status TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, url)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS monitor_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'homepage',
    url TEXT NOT NULL,
    selector TEXT,
    include_keywords TEXT,
    exclude_keywords TEXT,
    scan_interval_minutes INTEGER NOT NULL DEFAULT 60,
    enabled INTEGER NOT NULL DEFAULT 1,
    baseline_completed_at TEXT,
    product_baseline_completed_at TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    next_scan_after TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TEXT,
    last_status TEXT,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    UNIQUE(site_id, source_type, url)
);

CREATE TABLE IF NOT EXISTS known_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    title_hint TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE CASCADE,
    UNIQUE(source_id, url)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    source_id INTEGER,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    image_url TEXT,
    price TEXT,
    price_amount REAL,
    currency TEXT,
    compare_at_price REAL,
    availability TEXT,
    variant_count INTEGER,
    item_type TEXT NOT NULL DEFAULT 'unknown',
    review_status TEXT NOT NULL DEFAULT 'unreviewed',
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    discovery_status TEXT NOT NULL DEFAULT 'new',
    extraction_source TEXT NOT NULL DEFAULT 'unknown',
    confidence_score REAL NOT NULL DEFAULT 0,
    field_confidence_json TEXT NOT NULL DEFAULT '{}',
    confidence_reasons_json TEXT NOT NULL DEFAULT '[]',
    features_json TEXT NOT NULL DEFAULT '[]',
    content_hash TEXT NOT NULL,
    raw_text TEXT,
    detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    UNIQUE(site_id, url)
);

CREATE TABLE IF NOT EXISTS scan_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    source_id INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    candidates_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS scan_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_job_id INTEGER,
    site_id INTEGER NOT NULL,
    source_id INTEGER,
    job_type TEXT NOT NULL,
    trigger_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'queued',
    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT,
    candidates_count INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    message TEXT,
    result_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(parent_job_id) REFERENCES scan_jobs(id) ON DELETE SET NULL,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS source_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    selector TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_hash TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    extracted_text TEXT,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    product_id INTEGER,
    snapshot_before_id INTEGER,
    snapshot_after_id INTEGER NOT NULL,
    change_type TEXT NOT NULL DEFAULT 'text_change',
    severity TEXT NOT NULL DEFAULT 'normal',
    summary TEXT,
    diff_json TEXT NOT NULL DEFAULT '[]',
    inbox_status TEXT NOT NULL DEFAULT 'unread',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY(snapshot_before_id) REFERENCES source_snapshots(id) ON DELETE SET NULL,
    FOREIGN KEY(snapshot_after_id) REFERENCES source_snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notification_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER NOT NULL,
    product_id INTEGER,
    event_id INTEGER,
    event_type TEXT,
    channel TEXT NOT NULL DEFAULT 'webhook',
    target_url TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL,
    FOREIGN KEY(event_id) REFERENCES change_events(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    site_id INTEGER,
    source_id INTEGER,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    action TEXT NOT NULL,
    summary TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_products_detected_at
ON products(detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_sources_site_id
ON monitor_sources(site_id);

CREATE INDEX IF NOT EXISTS idx_known_urls_source_id
ON known_urls(source_id);

CREATE INDEX IF NOT EXISTS idx_scan_logs_started_at
ON scan_logs(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_status_queued
ON scan_jobs(status, queued_at DESC);

CREATE INDEX IF NOT EXISTS idx_scan_jobs_site_id
ON scan_jobs(site_id, queued_at DESC);

CREATE INDEX IF NOT EXISTS idx_source_snapshots_source_id
ON source_snapshots(source_id, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_change_events_created_at
ON change_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_status_next
ON notification_outbox(status, next_attempt_at);

DROP INDEX IF EXISTS idx_notification_outbox_product_target;

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
