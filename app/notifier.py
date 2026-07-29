from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from app.db import execute_sql, fetchall, get_db, insert_ignore, json_dumps, row_to_dict, update_by_id, where_in_clause
from app.url_safety import validate_public_http_url

DEFAULT_NOTIFICATION_EVENTS = {"product_new"}

EVENT_LABELS = {
    "product_new": "新增产品",
    "price_change": "价格变化",
    "availability_change": "库存变化",
    "description_change": "描述变化",
    "text_change": "页面文本变化",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def notification_payload(product: dict) -> dict:
    text = (
        "检测到官网新品发布\n\n"
        f"产品：{product.get('title')}\n"
        f"价格：{product.get('price') or '未识别'}\n"
        f"链接：{product.get('url')}\n\n"
        "核心卖点：\n"
        + "\n".join(f"- {item}" for item in product.get("features", [])[:5])
    )
    return {
        "msgtype": "text",
        "text": {"content": text},
        "product": product,
    }


def enabled_notification_events(site: dict) -> set[str]:
    raw = site.get("notification_events")
    if not raw:
        return set(DEFAULT_NOTIFICATION_EVENTS)
    return {str(item) for item in raw}


def should_notify_event(site: dict, event_type: str) -> bool:
    return bool(site.get("webhook_url")) and event_type in enabled_notification_events(site)


def change_event_payload(event: dict, product: dict | None = None) -> dict:
    label = EVENT_LABELS.get(event.get("change_type"), event.get("change_type") or "变化")
    title = (product or {}).get("title") or event.get("summary") or label
    url = (product or {}).get("url") or event.get("source_url")
    text = (
        f"{label}\n\n"
        f"标题：{title}\n"
        f"摘要：{event.get('summary') or ''}\n"
        f"链接：{url or ''}"
    )
    return {
        "msgtype": "text",
        "text": {"content": text},
        "event": event,
        "product": product,
    }


def enqueue_change_event_notification(
    site_id: int,
    product_id: int | None,
    event_id: int,
    event_type: str,
    webhook_url: str | None,
    event: dict,
    product: dict | None = None,
) -> int | None:
    if not webhook_url:
        return None
    safe_webhook_url = validate_public_http_url(webhook_url)
    payload = change_event_payload(event, product)
    with get_db() as db:
        insert_ignore(
            db,
            "notification_outbox",
            ["site_id", "product_id", "event_id", "event_type", "channel", "target_url", "payload", "status", "next_attempt_at"],
            (
                site_id,
                product_id,
                event_id,
                event_type,
                "webhook",
                safe_webhook_url,
                json_dumps(payload),
                "pending",
                now_iso(),
            ),
        )
        row = execute_sql(
            db,
            """
            SELECT id FROM notification_outbox
            WHERE event_id = ? AND target_url = ?
            """,
            (event_id, safe_webhook_url),
        ).fetchone()
    return row["id"] if row else None


def enqueue_webhook_notification(site_id: int, product_id: int, webhook_url: str | None, product: dict) -> int | None:
    if not webhook_url:
        return None
    safe_webhook_url = validate_public_http_url(webhook_url)
    payload = notification_payload(product)
    with get_db() as db:
        insert_ignore(
            db,
            "notification_outbox",
            ["site_id", "product_id", "event_type", "channel", "target_url", "payload", "status", "next_attempt_at"],
            (
                site_id,
                product_id,
                "product_new",
                "webhook",
                safe_webhook_url,
                json_dumps(payload),
                "pending",
                now_iso(),
            ),
        )
        row = execute_sql(
            db,
            """
            SELECT id FROM notification_outbox
            WHERE product_id = ? AND target_url = ?
            """,
            (product_id, safe_webhook_url),
        ).fetchone()
    return row["id"] if row else None


async def send_webhook(webhook_url: str | None, payload: dict) -> None:
    if not webhook_url:
        return
    safe_webhook_url = validate_public_http_url(webhook_url)
    bodies = [payload]
    product = payload.get("product") if isinstance(payload, dict) else None
    if isinstance(product, dict):
        bodies.append({"text": payload.get("text", {}).get("content", ""), **product})

    async with httpx.AsyncClient(timeout=12) as client:
        last_error: Exception | None = None
        for body in bodies:
            try:
                res = await client.post(safe_webhook_url, json=body, follow_redirects=False)
                if res.status_code < 400:
                    return
                last_error = RuntimeError(f"Webhook 返回 HTTP {res.status_code}")
            except httpx.HTTPError as exc:
                last_error = exc
        if last_error:
            raise last_error


def _next_retry_time(attempts: int) -> str:
    delay_seconds = min(3600, 60 * (2 ** max(attempts - 1, 0)))
    return (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()


def _mark_notification_sent(notification_id: int) -> None:
    with get_db() as db:
        update_by_id(
            db,
            "notification_outbox",
            notification_id,
            {"status": "sent", "sent_at": now_iso(), "last_error": None},
        )


def _mark_notification_failed(notification_id: int, attempts: int, max_attempts: int, error: str) -> None:
    final_status = "failed" if attempts >= max_attempts else "pending"
    with get_db() as db:
        update_by_id(
            db,
            "notification_outbox",
            notification_id,
            {
                "status": final_status,
                "attempts": attempts,
                "next_attempt_at": _next_retry_time(attempts),
                "last_error": error[:1000],
            },
        )


def claim_pending_notifications(limit: int = 20) -> list[dict]:
    claimed_ids: list[int] = []
    with get_db() as db:
        rows = fetchall(
            db,
            """
            SELECT id, attempts
            FROM notification_outbox
            WHERE status = 'pending'
              AND next_attempt_at <= ?
            ORDER BY next_attempt_at ASC, id ASC
            LIMIT ?
            """,
            (now_iso(), limit),
        )
        for row in rows:
            cursor = execute_sql(
                db,
                """
                UPDATE notification_outbox
                SET status = 'sending', attempts = ?, last_error = NULL
                WHERE id = ? AND status = 'pending'
                """,
                (int(row["attempts"]) + 1, row["id"]),
            )
            if cursor.rowcount:
                claimed_ids.append(row["id"])
        if not claimed_ids:
            return []
        id_filter_sql, id_filter_values = where_in_clause("id", claimed_ids)
        claimed_rows = fetchall(
            db,
            f"""
            SELECT *
            FROM notification_outbox
            WHERE {id_filter_sql}
            ORDER BY next_attempt_at ASC, id ASC
            """,
            id_filter_values,
        )
    return [row_to_dict(row) for row in claimed_rows]


def load_pending_notifications(limit: int = 20) -> list[dict]:
    return claim_pending_notifications(limit)


async def process_pending_notifications(limit: int = 20, sender=send_webhook) -> int:
    notifications = claim_pending_notifications(limit)
    for notification in notifications:
        attempts = int(notification["attempts"])
        try:
            payload = notification.get("payload") or {}
            await sender(notification["target_url"], payload)
            _mark_notification_sent(notification["id"])
        except Exception as exc:
            _mark_notification_failed(
                notification["id"],
                attempts,
                int(notification["max_attempts"]),
                str(exc),
            )
    return len(notifications)


async def notification_worker_loop() -> None:
    while True:
        try:
            await process_pending_notifications()
        except Exception:
            pass
        await asyncio.sleep(15)
