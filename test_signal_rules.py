from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, fetchall, get_db, init_db, insert_row, json_dumps
from app.main import app
from app.monitor import enqueue_event_notification_if_enabled


class SignalRuleTests(unittest.TestCase):
    def test_notification_rule_persists_price_and_stock_conditions(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"signal-rule-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            registered = client.post("/api/auth/register", json={"email": email, "password": "test-password-123"})
            self.assertEqual(registered.status_code, 200, registered.text)
            response = client.post(
                "/api/notification-rules",
                headers={"Authorization": f"Bearer {registered.json()['token']}"},
                json={
                    "name": "在售低价提醒",
                    "channel": "wecom",
                    "target_url": "https://example.com/wecom-robot",
                    "event_types": ["price_change", "availability_change"],
                    "max_price_amount": 500,
                    "require_in_stock": True,
                },
            )

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["max_price_amount"], 500)
            self.assertTrue(response.json()["require_in_stock"])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))

    def test_delivery_rule_requires_price_limit_and_in_stock_product(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(db, "sites", {"user_id": 1, "name": "Signal rule store", "url": f"https://signals-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["price_change"])})
                source_id = insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "custom_page", "url": f"https://signals-{marker}.example.com/products", "scan_interval_minutes": 60})
                snapshot_id = insert_row(db, "source_snapshots", {"source_id": source_id, "url": f"https://signals-{marker}.example.com/products", "content_hash": marker, "text_hash": marker})
                insert_row(db, "notification_rules", {"user_id": 1, "site_id": site_id, "name": "Affordable and in stock", "channel": "wecom", "target_url": "https://example.com/wecom-robot", "event_types": json_dumps(["price_change"]), "min_severity": "normal", "inbox_status": "unread", "max_price_amount": 500, "require_in_stock": True, "enabled": True})

                event_ids: dict[str, int] = {}
                products = [
                    ("eligible", 499, "in_stock"),
                    ("too-expensive", 501, "in_stock"),
                    ("sold-out", 499, "out_of_stock"),
                ]
                for name, price, availability in products:
                    product_id = insert_row(db, "products", {"site_id": site_id, "url": f"https://signals-{marker}.example.com/{name}", "title": name, "price_amount": price, "currency": "CNY", "availability": availability, "content_hash": f"{name}-{marker}"})
                    event_id = insert_row(db, "change_events", {"site_id": site_id, "source_id": source_id, "product_id": product_id, "snapshot_after_id": snapshot_id, "change_type": "price_change", "severity": "normal", "summary": name})
                    event_ids[name] = event_id
                    enqueue_event_notification_if_enabled(
                        db,
                        {"site_id": site_id, "webhook_url": None, "notification_events": ["price_change"]},
                        event_id=event_id,
                        event_type="price_change",
                        product_id=product_id,
                        event={"id": event_id, "change_type": "price_change", "severity": "normal", "summary": name},
                        product={"id": product_id, "title": name, "price_amount": price, "currency": "CNY", "availability": availability},
                    )
                delivered = [row["event_id"] for row in fetchall(db, "SELECT event_id FROM notification_outbox WHERE event_id IN (?, ?, ?)", tuple(event_ids.values()))]

            self.assertEqual(delivered, [event_ids["eligible"]])
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


if __name__ == "__main__":
    unittest.main()
