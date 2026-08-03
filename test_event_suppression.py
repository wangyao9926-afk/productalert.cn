from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.crawler import ExtractedSourceText
from app.db import execute_sql, fetchone, get_db, init_db, insert_row
from app.main import app
from app.monitor import capture_source_snapshot


class EventSuppressionApiTests(unittest.TestCase):
    def test_owner_can_suppress_future_events_from_the_same_source_only(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"suppression-owner-{marker}@monitor.internal"
        stranger_email = f"suppression-stranger-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            stranger = client.post("/api/auth/register", json={"email": stranger_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(stranger.status_code, 200, stranger.text)
            with get_db() as db:
                site_id = insert_row(db, "sites", {"user_id": owner.json()["user"]["id"], "name": "Suppression site", "url": f"https://suppression-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"product_new\"]"})
                source_id = insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "custom_page", "url": f"https://suppression-{marker}.example.com/news", "scan_interval_minutes": 60})
                snapshot_id = insert_row(db, "source_snapshots", {"source_id": source_id, "url": f"https://suppression-{marker}.example.com/news", "content_hash": "content", "text_hash": "text"})
                event_id = insert_row(db, "change_events", {"site_id": site_id, "source_id": source_id, "snapshot_after_id": snapshot_id, "change_type": "text_change", "severity": "normal", "summary": "Banner changed"})

            owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
            stranger_headers = {"Authorization": f"Bearer {stranger.json()['token']}"}
            created = client.post(f"/api/change-events/{event_id}/suppress-similar", headers=owner_headers, json={"reason": "Rotating banner"})
            forbidden = client.post(f"/api/change-events/{event_id}/suppress-similar", headers=stranger_headers, json={"reason": "Not mine"})
            rules = client.get("/api/event-suppression-rules", headers=owner_headers)

            self.assertEqual(created.status_code, 200, created.text)
            self.assertEqual(created.json()["source_id"], source_id)
            self.assertEqual(created.json()["change_type"], "text_change")
            self.assertEqual(created.json()["reason"], "Rotating banner")
            self.assertEqual(forbidden.status_code, 404, forbidden.text)
            self.assertEqual(rules.status_code, 200, rules.text)
            self.assertEqual([rule["id"] for rule in rules.json()], [created.json()["id"]])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, stranger_email))


class EventSuppressionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_suppressed_source_change_keeps_evidence_without_creating_event_or_notification(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(db, "sites", {"user_id": 1, "name": "Suppression runtime", "url": f"https://runtime-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"text_change\"]"})
                source_id = insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "custom_page", "url": f"https://runtime-{marker}.example.com/news", "scan_interval_minutes": 60})
                insert_row(db, "source_snapshots", {"source_id": source_id, "url": f"https://runtime-{marker}.example.com/news", "content_hash": "old-content", "text_hash": "old-text", "extracted_text": "Old banner"})
                insert_row(db, "event_suppression_rules", {"site_id": site_id, "source_id": source_id, "change_type": "text_change", "reason": "Rotating banner", "enabled": True})
            source_data = {"id": source_id, "site_id": site_id, "url": f"https://runtime-{marker}.example.com/news", "selector": None, "notification_events": ["text_change"]}
            extracted = ExtractedSourceText(
                url=source_data["url"],
                selector=None,
                text="New banner",
                content_hash="new-content",
                text_hash="new-text",
                capture_method="http",
                http_status=200,
                content_type="text/html",
                content_length=12,
            )
            with patch("app.monitor.extract_source_text", new=AsyncMock(return_value=extracted)), patch("app.monitor.try_render_page", new=AsyncMock(return_value=None)):
                result = await capture_source_snapshot(source_data, baseline_mode=False, notify=True)

            assert result is not None
            self.assertTrue(result["changed"])
            self.assertTrue(result["suppressed"])
            with get_db() as db:
                event_count = fetchone(db, "SELECT COUNT(*) AS count FROM change_events WHERE source_id = ?", (source_id,))["count"]
                notification_count = fetchone(db, "SELECT COUNT(*) AS count FROM notification_outbox WHERE site_id = ?", (site_id,))["count"]
            self.assertEqual(event_count, 0)
            self.assertEqual(notification_count, 0)
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


if __name__ == "__main__":
    unittest.main()
