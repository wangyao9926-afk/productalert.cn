CREATE TABLE IF NOT EXISTS runtime_heartbeats (
    component TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL
);
