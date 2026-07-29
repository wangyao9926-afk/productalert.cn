from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import execute_sql, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.notifier import now_iso, process_pending_notifications


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def create_failed_notification(site_id: int, marker: str) -> int:
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
                "attempts": 5,
                "max_attempts": 5,
                "next_attempt_at": now_iso(),
                "last_error": "previous failure",
            },
        )


def load_notification(notification_id: int) -> dict:
    with get_db() as db:
        row = fetchone(db, "SELECT * FROM notification_outbox WHERE id = ?", (notification_id,))
    if row is None:
        raise RuntimeError(f"notification {notification_id} was not found")
    return row_to_dict(row)


def audit_log_exists(notification_id: int) -> bool:
    with get_db() as db:
        row = fetchone(
            db,
            """
            SELECT id
            FROM audit_logs
            WHERE action = 'notification.retry'
              AND entity_type = 'notification'
              AND entity_id = ?
            """,
            (notification_id,),
        )
    return row is not None


def run_smoke_test() -> dict:
    init_db()
    marker = uuid4().hex
    email = f"notification-retry-smoke-{marker}@monitor.internal"
    password = "smoke-test-password"
    client = TestClient(main_module.app)
    original_processor = main_module.process_pending_notifications
    deliveries: list[dict] = []
    site_id: int | None = None
    notification_id: int | None = None

    async def capture_sender(target_url: str, payload: dict) -> None:
        deliveries.append({"target_url": target_url, "payload": payload})

    async def fake_processor(limit: int = 20) -> int:
        return await process_pending_notifications(limit=limit, sender=capture_sender)

    try:
        register = client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        assert_status(register, 200, "register")
        token = register.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        site = client.post(
            "/api/sites",
            headers=headers,
            json={
                "name": "Notification Retry Smoke Site",
                "url": f"https://1.1.1.1/{marker}",
                "scan_interval_minutes": 60,
                "notification_events": ["product_new"],
            },
        )
        assert_status(site, 200, "create site")
        site_id = site.json()["id"]
        notification_id = create_failed_notification(site_id, marker)

        main_module.process_pending_notifications = fake_processor
        retry = client.post(f"/api/notifications/{notification_id}/retry", headers=headers)
        assert_status(retry, 200, "retry notification")
        response_data = retry.json()
        notification = load_notification(notification_id)

        if response_data.get("status") != "sent":
            raise RuntimeError(f"retry response status should be sent, got {response_data.get('status')}")
        if notification.get("status") != "sent":
            raise RuntimeError(f"retried notification should be sent, got {notification.get('status')}")
        if int(notification.get("attempts") or 0) != 1:
            raise RuntimeError(f"retried notification should restart attempts at 1, got {notification.get('attempts')}")
        if notification.get("last_error"):
            raise RuntimeError(f"retried notification kept last_error: {notification.get('last_error')}")
        if not notification.get("sent_at"):
            raise RuntimeError("retried notification did not record sent_at")
        if len(deliveries) != 1:
            raise RuntimeError(f"expected one delivery, got {len(deliveries)}")
        if deliveries[0]["payload"].get("marker") != marker:
            raise RuntimeError("retried delivery payload marker did not match")
        if not audit_log_exists(notification_id):
            raise RuntimeError("notification retry audit log was not recorded")

        return {
            "notification_id": notification_id,
            "status": notification.get("status"),
            "attempts": notification.get("attempts"),
        }
    finally:
        main_module.process_pending_notifications = original_processor
        if site_id is not None:
            client.delete(f"/api/sites/{site_id}", headers=locals().get("headers", {}))
        cleanup_user(email)


def main() -> None:
    result = run_smoke_test()
    print(
        "notification retry smoke ok "
        f"notification_id={result['notification_id']} "
        f"status={result['status']} "
        f"attempts={result['attempts']}"
    )


if __name__ == "__main__":
    main()
