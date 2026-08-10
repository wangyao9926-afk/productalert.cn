from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db
from app.main import app


class RealSiteBenchmarkApiTests(unittest.TestCase):
    def test_authenticated_user_can_read_real_site_reference_registry_without_accuracy_claim(self) -> None:
        init_db()
        email = f"real-site-benchmark-{uuid4().hex}@monitor.internal"
        client = TestClient(app)
        try:
            register = client.get("/api/real-site-benchmark")
            self.assertEqual(register.status_code, 401)

            auth = client.post("/api/auth/register", json={"email": email, "password": "benchmark-password"})
            response = client.get("/api/real-site-benchmark", headers={"Authorization": f"Bearer {auth.json()['token']}"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["core_site_count"], 10)
            self.assertEqual(payload["control_site_count"], 1)
            self.assertEqual(payload["public_catalog_reference_count"], 5)
            self.assertFalse(payload["accuracy_claim_allowed"])
            self.assertIn("人工确认", payload["next_action"])
            fanttik = next(item for item in payload["sites"] if item["slug"] == "fanttik")
            self.assertEqual(fanttik["reference_count"], 212)
            self.assertEqual(fanttik["reference_state"], "public_catalog_count")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
