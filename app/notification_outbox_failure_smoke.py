from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.db import execute_sql, fetchall, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.notifier import now_iso, process_pending_notifications


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def create_site(email: str, marker: str) -> int:
    with get_db() as db:
        user_id = insert_row(
            db,
            "users",
            {
                "email": email,
                "password_hash": "notification-failure-smoke",
            },
        )
        return insert_row(
            db,
            "sites",
            {
                "user_id": user_id,
                "name": "Notification Failure Smoke Site",
                "url": f"https://example.com/{marker}",
                "scan_interval_minutes": 60,
                "webhook_url": "https://example.com/webhook",
                "notification_events": json_dumps(["product_new"]),
            },
        )


def create_notification(site_id: int, marker: str, max_attempts: int) -> int:
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
                "status": "pending",
                "max_attempts": max_attempts,
                "next_attempt_at": now_iso(),
            },
        )


def load_notifications(notification_ids: list[int]) -> dict[int, dict]:
    placeholders = ", ".join("?" for _ in notification_ids)
    with get_db() as db:
        rows = fetchall(
            db,
            f"SELECT * FROM notification_outbox WHERE id IN ({placeholders})",
            notification_ids,
        )
    return {int(row["id"]): row_to_dict(row) for row in rows}


def parse_iso(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


async def run_smoke_test() -> dict:
    init_db()
    marker = uuid4().hex
    email = f"notification-failure-smoke-{marker}@monitor.internal"
    site_id = create_site(email, marker)
    retry_notification_id = create_notification(site_id, f"{marker}-retry", max_attempts=5)
    failed_notification_id = create_notification(site_id, f"{marker}-failed", max_attempts=1)
    started_at = datetime.now(timezone.utc)
    attempts: list[dict] = []

    async def failing_sender(target_url: str, payload: dict) -> None:
        attempts.append({"target_url": target_url, "payload": payload})
        raise RuntimeError("smoke webhook failure")

    try:
        processed_count = await process_pending_notifications(limit=10, sender=failing_sender)
        notifications = load_notifications([retry_notification_id, failed_notification_id])
        if processed_count != 2:
            raise RuntimeError(f"expected two notifications to be processed, got {processed_count}")
        if len(attempts) != 2:
            raise RuntimeError(f"expected two delivery attempts, got {len(attempts)}")

        retry_notification = notifications[retry_notification_id]
        if retry_notification.get("status") != "pending":
            raise RuntimeError(f"expected retry notification to return pending, got {retry_notification.get('status')}")
        if int(retry_notification.get("attempts") or 0) != 1:
            raise RuntimeError(f"expected retry notification attempts=1, got {retry_notification.get('attempts')}")
        if "smoke webhook failure" not in (retry_notification.get("last_error") or ""):
            raise RuntimeError("retry notification did not record last_error")
        if retry_notification.get("sent_at"):
            raise RuntimeError("retry notification unexpectedly recorded sent_at")
        retry_next_attempt = parse_iso(retry_notification["next_attempt_at"])
        if retry_next_attempt <= started_at:
            raise RuntimeError("retry notification next_attempt_at was not moved into the future")

        failed_notification = notifications[failed_notification_id]
        if failed_notification.get("status") != "failed":
            raise RuntimeError(f"expected terminal notification to become failed, got {failed_notification.get('status')}")
        if int(failed_notification.get("attempts") or 0) != 1:
            raise RuntimeError(f"expected failed notification attempts=1, got {failed_notification.get('attempts')}")
        if "smoke webhook failure" not in (failed_notification.get("last_error") or ""):
            raise RuntimeError("failed notification did not record last_error")
        if failed_notification.get("sent_at"):
            raise RuntimeError("failed notification unexpectedly recorded sent_at")

        return {
            "processed_count": processed_count,
            "retry_status": retry_notification.get("status"),
            "failed_status": failed_notification.get("status"),
        }
    finally:
        cleanup_user(email)


def main() -> None:
    result = asyncio.run(run_smoke_test())
    print(
        "notification outbox failure smoke ok "
        f"processed={result['processed_count']} "
        f"retry_status={result['retry_status']} "
        f"failed_status={result['failed_status']}"
    )


if __name__ == "__main__":
    main()
