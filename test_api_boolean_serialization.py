from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db
from app.main import app


class ApiBooleanSerializationTests(unittest.TestCase):
    def test_source_enabled_is_returned_as_a_json_boolean_after_update(self) -> None:
        """SQLite storage integers must not leak through the public API."""
        init_db()
        marker = uuid4().hex
        email = f"boolean-contract-{marker}@monitor.internal"
        client = TestClient(app)

        try:
            registered = client.post(
                "/api/auth/register",
                json={"email": email, "password": "test-password-123"},
            )
            self.assertEqual(registered.status_code, 200, registered.text)
            headers = {"Authorization": f"Bearer {registered.json()['token']}"}

            site = client.post(
                "/api/sites",
                headers=headers,
                json={"name": "Boolean contract", "url": f"https://1.1.1.1/{marker}"},
            )
            self.assertEqual(site.status_code, 200, site.text)
            source = client.post(
                f"/api/sites/{site.json()['id']}/sources",
                headers=headers,
                json={"source_type": "custom_page", "url": f"https://1.0.0.1/{marker}/source"},
            )
            self.assertEqual(source.status_code, 200, source.text)

            updated = client.patch(
                f"/api/sources/{source.json()['id']}",
                headers=headers,
                json={"enabled": False},
            )
            self.assertEqual(updated.status_code, 200, updated.text)

            sources = client.get("/api/sites", headers=headers)
            self.assertEqual(sources.status_code, 200, sources.text)
            saved_site = next(item for item in sources.json() if item["id"] == site.json()["id"])
            saved_source = next(item for item in saved_site["sources"] if item["id"] == source.json()["id"])
            self.assertIs(saved_source["enabled"], False)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
