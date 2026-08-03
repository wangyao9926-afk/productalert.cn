CREATE TABLE IF NOT EXISTS scan_job_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    site_id INTEGER NOT NULL,
    source_id INTEGER,
    url TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    http_status INTEGER,
    error_category TEXT,
    retry_after_seconds INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(job_id) REFERENCES scan_jobs(id) ON DELETE CASCADE,
    FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
    FOREIGN KEY(source_id) REFERENCES monitor_sources(id) ON DELETE SET NULL,
    UNIQUE(job_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS idx_scan_job_candidates_job_status
ON scan_job_candidates(job_id, status);

CREATE INDEX IF NOT EXISTS idx_scan_job_candidates_site_status
ON scan_job_candidates(site_id, status);
