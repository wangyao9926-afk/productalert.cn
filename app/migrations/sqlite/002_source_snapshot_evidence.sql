ALTER TABLE source_snapshots ADD COLUMN capture_method TEXT NOT NULL DEFAULT 'http';
ALTER TABLE source_snapshots ADD COLUMN http_status INTEGER;
ALTER TABLE source_snapshots ADD COLUMN content_type TEXT;
ALTER TABLE source_snapshots ADD COLUMN content_length INTEGER NOT NULL DEFAULT 0;
