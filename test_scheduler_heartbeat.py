from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db
from app.main import app
from app.runtime_health import record_runtime_heartbeat, runtime_component_health


class SchedulerHeartbeatTests(unittest.TestCase):
    def test_runtime_heartbeat_reports_fresh_and_stale_components(self) -> None:
        init_db()
        component = f"scheduler-test-{uuid4().hex}"
        recorded_at = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)

        try:
            record_runtime_heartbeat(component, recorded_at)

            fresh = runtime_component_health(
                component,
                now=recorded_at + timedelta(seconds=179),
                stale_after_seconds=180,
            )
            stale = runtime_component_health(
                component,
                now=recorded_at + timedelta(seconds=181),
                stale_after_seconds=180,
            )

            self.assertEqual(fresh["last_seen_at"], recorded_at.isoformat())
            self.assertTrue(fresh["healthy"])
            self.assertFalse(stale["healthy"])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM runtime_heartbeats WHERE component = ?", (component,))

    def test_system_health_exposes_scheduler_liveness(self) -> None:
        client = TestClient(app)
        email = f"scheduler-health-{uuid4().hex}@monitor.internal"
        register = client.post("/api/auth/register", json={"email": email, "password": "test-password-123"})
        self.assertEqual(register.status_code, 200, register.text)

        try:
            with patch(
                "app.main.runtime_component_health",
                return_value={"component": "scheduler", "last_seen_at": "2026-08-20T00:00:00+00:00", "healthy": True},
            ):
                response = client.get("/api/system/health", headers={"Authorization": f"Bearer {register.json()['token']}"})

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["scheduler"],
                {"required": True, "last_seen_at": "2026-08-20T00:00:00+00:00", "healthy": True},
            )
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
