ALTER TABLE change_events
ADD COLUMN IF NOT EXISTS assignee TEXT;

ALTER TABLE change_events
ADD COLUMN IF NOT EXISTS review_note TEXT;

ALTER TABLE change_events
ADD COLUMN IF NOT EXISTS false_positive_reason TEXT;

ALTER TABLE change_events
ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
