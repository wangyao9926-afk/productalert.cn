from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db
from app.main import app


class QualityBenchmarkApiTests(unittest.TestCase):
    def test_authenticated_user_can_read_controlled_extraction_benchmark(self) -> None:
        init_db()
        email = f"benchmark-api-{uuid4().hex}@monitor.internal"
        client = TestClient(app)
        try:
            register = client.post("/api/auth/register", json={"email": email, "password": "benchmark-password"})
            self.assertEqual(register.status_code, 200)

            response = client.get("/api/quality-benchmark", headers={"Authorization": f"Bearer {register.json()['token']}"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["scope"], "controlled_fixture")
            self.assertGreaterEqual(payload["case_count"], 3)
            self.assertIn("price_amount", payload["field_pass_rates"])
            self.assertIn("woocommerce_store_api", payload["coverage"])
            self.assertIn("线上真实站点", payload["limitation"])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
