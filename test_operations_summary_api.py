from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app, parse_observability_time


class OperationsSummaryApiTests(unittest.TestCase):
    def test_observability_time_accepts_postgresql_datetime_values(self) -> None:
        recorded_at = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(parse_observability_time(recorded_at), recorded_at)

    def test_owner_receives_scan_queue_notification_and_failure_summary(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"operations-summary-{marker}@monitor.internal"
        client = TestClient(app)

        try:
            register = client.post("/api/auth/register", json={"email": email, "password": "test-password-123"})
            self.assertEqual(register.status_code, 200, register.text)
            headers = {"Authorization": f"Bearer {register.json()['token']}"}
            user_id = register.json()["user"]["id"]
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": user_id,
                        "name": "Operations summary site",
                        "url": f"https://ops-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": "[\"product_new\"]",
                    },
                )
                insert_row(
                    db,
                    "scan_logs",
                    {
                        "site_id": site_id,
                        "started_at": "2026-07-30T00:00:00+00:00",
                        "finished_at": "2026-07-30T00:00:02+00:00",
                        "status": "success",
                        "mode": "site",
                        "message": "Scan complete",
                    },
                )
                insert_row(
                    db,
                    "scan_logs",
                    {
                        "site_id": site_id,
                        "started_at": "2026-07-30T01:00:00+00:00",
                        "finished_at": "2026-07-30T01:00:05+00:00",
                        "status": "failed",
                        "mode": "site",
                        "message": "HTTP 403 blocked by target",
                    },
                )
                for status in ("queued", "running", "failed"):
                    insert_row(
                        db,
                        "scan_jobs",
                        {
                            "site_id": site_id,
                            "job_type": "site_scan",
                            "trigger_type": "manual",
                            "status": status,
                        },
                    )
                for status in ("pending", "failed"):
                    insert_row(
                        db,
                        "notification_outbox",
                        {
                            "site_id": site_id,
                            "channel": "webhook",
                            "target_url": f"https://hooks-{marker}.example.com/{status}",
                            "payload": json_dumps({}),
                            "status": status,
                        },
                    )

            response = client.get("/api/operations/summary", headers=headers)

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["scans"]["total"], 2)
            self.assertEqual(payload["scans"]["successful"], 1)
            self.assertEqual(payload["scans"]["failed"], 1)
            self.assertEqual(payload["scans"]["success_rate"], 0.5)
            self.assertEqual(payload["scans"]["average_duration_ms"], 3500)
            self.assertEqual(payload["queue"], {"queued": 1, "running": 1, "failed": 1})
            self.assertEqual(payload["notifications"], {"pending": 1, "sending": 0, "failed": 1})
            self.assertEqual(payload["failure_categories"], [{"category": "access_denied", "count": 1}])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
