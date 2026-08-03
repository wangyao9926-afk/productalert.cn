CREATE TABLE IF NOT EXISTS scan_job_candidates (
    id BIGSERIAL PRIMARY KEY,
    job_id BIGINT NOT NULL REFERENCES scan_jobs(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    source_id BIGINT REFERENCES monitor_sources(id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    http_status INTEGER,
    error_category TEXT,
    retry_after_seconds INTEGER,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    payload_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, canonical_key)
);

CREATE INDEX IF NOT EXISTS idx_scan_job_candidates_job_status
ON scan_job_candidates(job_id, status);

CREATE INDEX IF NOT EXISTS idx_scan_job_candidates_site_status
ON scan_job_candidates(site_id, status);
