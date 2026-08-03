from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app


class CatalogQualityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        marker = uuid4().hex
        self.owner_email = f"resume-owner-{marker}@monitor.internal"
        self.other_email = f"resume-other-{marker}@monitor.internal"
        self.owner_client = TestClient(app)
        self.other_client = TestClient(app)
        owner = self.owner_client.post("/api/auth/register", json={"email": self.owner_email, "password": "test-password-123"})
        other = self.other_client.post("/api/auth/register", json={"email": self.other_email, "password": "test-password-123"})
        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertEqual(other.status_code, 200, other.text)
        self.owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
        self.other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
        with get_db() as db:
            self.site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": owner.json()["user"]["id"],
                    "name": "Incomplete catalog",
                    "url": f"https://resume-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": json_dumps(["product_new"]),
                },
            )
            insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": self.site_id,
                    "source_type": "homepage",
                    "url": f"https://resume-{marker}.example.com",
                    "scan_interval_minutes": 60,
                },
            )
            self.job_id = insert_row(
                db,
                "scan_jobs",
                {
                    "site_id": self.site_id,
                    "job_type": "site_scan",
                    "trigger_type": "baseline",
                    "status": "partial_success",
                    "result": json_dumps(
                        {
                            "progress": {
                                "baseline_completed": False,
                                "quality": {"baseline_state": "incomplete", "rate_limited_count": 3},
                            }
                        }
                    ),
                },
            )

    def tearDown(self) -> None:
        with get_db() as db:
            execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (self.owner_email, self.other_email))

    def test_owner_can_resume_incomplete_baseline(self) -> None:
        response = self.owner_client.post(f"/api/scan-jobs/{self.job_id}/resume", headers=self.owner_headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["resume_of_job_id"], self.job_id)

    def test_other_user_cannot_resume_incomplete_baseline(self) -> None:
        response = self.other_client.post(f"/api/scan-jobs/{self.job_id}/resume", headers=self.other_headers)

        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
