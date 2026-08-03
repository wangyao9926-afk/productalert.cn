ALTER TABLE notification_rules ADD COLUMN max_price_amount REAL;
ALTER TABLE notification_rules ADD COLUMN require_in_stock INTEGER NOT NULL DEFAULT 0;
