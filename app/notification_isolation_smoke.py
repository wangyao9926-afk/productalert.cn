from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app
from app.notifier import now_iso


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def register_user(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "smoke-test-password"},
    )
    assert_status(response, 200, f"register {email}")
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def create_site(client: TestClient, headers: dict, marker: str) -> int:
    response = client.post(
        "/api/sites",
        headers=headers,
        json={
            "name": f"Notification Isolation {marker}",
            "url": f"https://1.1.1.1/{marker}",
            "scan_interval_minutes": 60,
            "notification_events": ["product_new"],
        },
    )
    assert_status(response, 200, "create site")
    return int(response.json()["id"])


def create_notification(site_id: int, marker: str) -> int:
    with get_db() as db:
        return insert_row(
            db,
            "notification_outbox",
            {
                "site_id": site_id,
                "event_type": "product_new",
                "channel": "webhook",
                "target_url": "https://example.com/webhook",
                "payload": json_dumps({"marker": marker, "msgtype": "text"}),
                "status": "failed",
                "attempts": 1,
                "max_attempts": 1,
                "next_attempt_at": now_iso(),
                "last_error": f"isolation failure {marker}",
            },
        )


def run_smoke_test() -> dict:
    init_db()
    marker = uuid4().hex
    owner_email = f"notification-owner-{marker}@monitor.internal"
    stranger_email = f"notification-stranger-{marker}@monitor.internal"
    client = TestClient(app)
    owner_site_id: int | None = None

    try:
        owner_headers = register_user(client, owner_email)
        stranger_headers = register_user(client, stranger_email)
        owner_site_id = create_site(client, owner_headers, f"{marker}-owner")
        notification_id = create_notification(owner_site_id, marker)

        owner_notifications = client.get("/api/notifications", headers=owner_headers)
        assert_status(owner_notifications, 200, "owner list notifications")
        if not any(item["id"] == notification_id for item in owner_notifications.json()):
            raise RuntimeError("owner could not see their notification")

        stranger_notifications = client.get("/api/notifications", headers=stranger_headers)
        assert_status(stranger_notifications, 200, "stranger list notifications")
        if any(item["id"] == notification_id for item in stranger_notifications.json()):
            raise RuntimeError("stranger could see another user's notification")

        stranger_export = client.get("/api/export/notifications.csv", headers=stranger_headers)
        assert_status(stranger_export, 200, "stranger export notifications")
        if marker in stranger_export.text or str(notification_id) in stranger_export.text:
            raise RuntimeError("stranger export leaked another user's notification")

        stranger_retry = client.post(f"/api/notifications/{notification_id}/retry", headers=stranger_headers)
        assert_status(stranger_retry, 404, "stranger retry notification")

        return {
            "notification_id": notification_id,
            "owner_visible": True,
            "stranger_blocked": True,
        }
    finally:
        if owner_site_id is not None:
            client.delete(f"/api/sites/{owner_site_id}", headers=locals().get("owner_headers", {}))
        cleanup_user(owner_email)
        cleanup_user(stranger_email)


def main() -> None:
    result = run_smoke_test()
    print(
        "notification isolation smoke ok "
        f"notification_id={result['notification_id']} "
        f"owner_visible={result['owner_visible']} "
        f"stranger_blocked={result['stranger_blocked']}"
    )


if __name__ == "__main__":
    main()
