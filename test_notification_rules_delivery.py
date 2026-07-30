from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.main import app
from app.monitor import enqueue_event_notification_if_enabled


class NotificationRuleDeliveryTests(unittest.TestCase):
    def test_matching_wecom_rule_creates_channel_specific_outbox_job(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(db, "sites", {"user_id": 1, "name": "Rule delivery", "url": f"https://rules-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"price_change\"]"})
                source_id = insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "custom_page", "url": f"https://rules-{marker}.example.com/new", "scan_interval_minutes": 60})
                snapshot_id = insert_row(db, "source_snapshots", {"source_id": source_id, "url": f"https://rules-{marker}.example.com/new", "content_hash": "content", "text_hash": "text"})
                event_id = insert_row(db, "change_events", {"site_id": site_id, "source_id": source_id, "snapshot_after_id": snapshot_id, "change_type": "price_change", "severity": "high", "summary": "Price changed"})
                rule_url = "https://example.com/wecom-robot"
                insert_row(db, "notification_rules", {"user_id": 1, "site_id": site_id, "name": "Price robot", "channel": "wecom", "target_url": rule_url, "event_types": json_dumps(["price_change"]), "min_severity": "high", "inbox_status": "unread", "enabled": True})
                enqueue_event_notification_if_enabled(
                    db,
                    {"site_id": site_id, "webhook_url": None, "notification_events": ["price_change"]},
                    event_id=event_id,
                    event_type="price_change",
                    product_id=None,
                    event={"id": event_id, "change_type": "price_change", "severity": "high", "summary": "Price changed"},
                    product=None,
                )
                outbox = row_to_dict(fetchone(db, "SELECT * FROM notification_outbox WHERE event_id = ?", (event_id,)))

            self.assertEqual(outbox["channel"], "wecom")
            self.assertEqual(outbox["target_url"], rule_url)
            self.assertEqual(outbox["event_type"], "price_change")
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))

    def test_email_rule_is_rejected_until_a_real_email_sender_exists(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"rule-owner-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            registered = client.post("/api/auth/register", json={"email": email, "password": "test-password-123"})
            self.assertEqual(registered.status_code, 200, registered.text)
            headers = {"Authorization": f"Bearer {registered.json()['token']}"}
            response = client.post(
                "/api/notification-rules",
                headers=headers,
                json={
                    "name": "Email sender",
                    "channel": "email",
                    "target_url": "ops@example.com",
                    "event_types": ["price_change"],
                },
            )
            self.assertEqual(response.status_code, 400, response.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
