from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app


class BaselineScanProgressApiTests(unittest.TestCase):
    def test_owner_can_read_running_baseline_scan_progress(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"baseline-owner-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            registered = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            self.assertEqual(registered.status_code, 200, registered.text)
            headers = {"Authorization": f"Bearer {registered.json()['token']}"}
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": registered.json()["user"]["id"],
                        "name": "Baseline scan site",
                        "url": f"https://baseline-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new"]),
                    },
                )
                job_id = insert_row(
                    db,
                    "scan_jobs",
                    {
                        "site_id": site_id,
                        "job_type": "site_scan",
                        "trigger_type": "baseline",
                        "status": "running",
                        "result": json_dumps(
                            {
                                "progress": {
                                    "phase": "extracting_products",
                                    "discovered_count": 12,
                                    "processed_count": 5,
                                    "failed_count": 1,
                                    "product_count": 5,
                                }
                            }
                        ),
                    },
                )

            response = client.get(f"/api/scan-jobs/{job_id}", headers=headers)

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["result"]["progress"]["processed_count"], 5)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (owner_email,))

    def test_other_user_cannot_read_baseline_scan_progress(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"baseline-owner-{marker}@monitor.internal"
        other_email = f"baseline-other-{marker}@monitor.internal"
        owner_client = TestClient(app)
        other_client = TestClient(app)
        try:
            owner = owner_client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            other = other_client.post("/api/auth/register", json={"email": other_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(other.status_code, 200, other.text)
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": owner.json()["user"]["id"],
                        "name": "Private baseline scan site",
                        "url": f"https://private-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new"]),
                    },
                )
                job_id = insert_row(
                    db,
                    "scan_jobs",
                    {"site_id": site_id, "job_type": "site_scan", "trigger_type": "baseline", "status": "running"},
                )

            response = other_client.get(f"/api/scan-jobs/{job_id}", headers={"Authorization": f"Bearer {other.json()['token']}"})

            self.assertEqual(response.status_code, 404, response.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, other_email))


if __name__ == "__main__":
    unittest.main()
