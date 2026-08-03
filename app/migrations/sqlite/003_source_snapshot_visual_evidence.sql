ALTER TABLE source_snapshots ADD COLUMN screenshot_hash TEXT;
ALTER TABLE source_snapshots ADD COLUMN screenshot_path TEXT;
ALTER TABLE source_snapshots ADD COLUMN visual_change_ratio REAL;
ALTER TABLE source_snapshots ADD COLUMN screenshot_error TEXT;
