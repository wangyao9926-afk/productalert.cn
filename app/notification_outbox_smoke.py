from __future__ import annotations

import asyncio
from uuid import uuid4

from app.db import execute_sql, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.notifier import now_iso, process_pending_notifications


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def create_pending_notification(marker: str) -> tuple[int, str]:
    email = f"notification-smoke-{marker}@monitor.internal"
    with get_db() as db:
        user_id = insert_row(
            db,
            "users",
            {
                "email": email,
                "password_hash": "notification-smoke",
            },
        )
        site_id = insert_row(
            db,
            "sites",
            {
                "user_id": user_id,
                "name": "Notification Smoke Site",
                "url": f"https://example.com/{marker}",
                "scan_interval_minutes": 60,
                "webhook_url": "https://example.com/webhook",
                "notification_events": json_dumps(["product_new"]),
            },
        )
        notification_id = insert_row(
            db,
            "notification_outbox",
            {
                "site_id": site_id,
                "event_type": "product_new",
                "channel": "webhook",
                "target_url": "https://example.com/webhook",
                "payload": json_dumps({"marker": marker, "msgtype": "text"}),
                "status": "pending",
                "next_attempt_at": now_iso(),
            },
        )
    return notification_id, email


def load_notification(notification_id: int) -> dict:
    with get_db() as db:
        row = fetchone(db, "SELECT * FROM notification_outbox WHERE id = ?", (notification_id,))
    if row is None:
        raise RuntimeError(f"notification {notification_id} was not found")
    return row_to_dict(row)


async def run_smoke_test() -> dict:
    init_db()
    marker = uuid4().hex
    notification_id, email = create_pending_notification(marker)
    delivered: list[dict] = []

    async def capture_sender(target_url: str, payload: dict) -> None:
        delivered.append({"target_url": target_url, "payload": payload})

    try:
        processed_count = await process_pending_notifications(limit=1, sender=capture_sender)
        notification = load_notification(notification_id)
        if processed_count != 1:
            raise RuntimeError(f"expected one notification to be processed, got {processed_count}")
        if len(delivered) != 1:
            raise RuntimeError(f"expected one notification delivery, got {len(delivered)}")
        if delivered[0]["payload"].get("marker") != marker:
            raise RuntimeError("delivered payload marker did not match")
        if notification.get("status") != "sent":
            raise RuntimeError(f"expected notification status sent, got {notification.get('status')}")
        if int(notification.get("attempts") or 0) != 1:
            raise RuntimeError(f"expected one delivery attempt, got {notification.get('attempts')}")
        if not notification.get("sent_at"):
            raise RuntimeError("sent notification did not record sent_at")
        if notification.get("last_error"):
            raise RuntimeError(f"sent notification kept last_error: {notification.get('last_error')}")
        return {
            "notification_id": notification_id,
            "status": notification.get("status"),
            "attempts": notification.get("attempts"),
        }
    finally:
        cleanup_user(email)


def main() -> None:
    result = asyncio.run(run_smoke_test())
    print(
        "notification outbox smoke ok "
        f"notification_id={result['notification_id']} "
        f"status={result['status']} "
        f"attempts={result['attempts']}"
    )


if __name__ == "__main__":
    main()
