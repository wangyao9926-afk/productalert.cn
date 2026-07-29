ALTER TABLE change_events ADD COLUMN assignee TEXT;
ALTER TABLE change_events ADD COLUMN review_note TEXT;
ALTER TABLE change_events ADD COLUMN false_positive_reason TEXT;
ALTER TABLE change_events ADD COLUMN reviewed_at TEXT;
