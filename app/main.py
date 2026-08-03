from __future__ import annotations

import asyncio
import csv
import io
import json
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth import (
    CurrentUser,
    check_login_rate_limit,
    clear_failed_login,
    clear_session_cookie,
    create_session,
    hash_password,
    normalize_email,
    public_user,
    record_failed_login,
    revoke_session_token,
    set_session_cookie,
    verify_password,
)
from app.db import ROOT, assignment_list, execute_sql, fetchall, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict, select_by_id, update_by_id
from app.evidence_store import evidence_path
from app.monitor import create_site, create_source, scan_site, scan_source, scheduler_loop
from app.notifier import notification_worker_loop, process_pending_notifications
from app.settings import database_settings, queue_settings, runtime_settings
from app.task_queue import enqueue_site_scan, enqueue_source_scan, queue_backend_name, scan_worker_loop
from app.url_safety import UnsafeUrlError, validate_public_http_url


app = FastAPI(title="官网新品情报监控系统")
STATIC_DIR = ROOT / "static"

SourceType = Literal["homepage", "sitemap", "rss", "listing_page", "news_page", "custom_page"]
SeverityLevel = Literal["low", "normal", "high", "critical"]
InboxStatus = Literal["unread", "important", "read", "false_positive", "follow_up"]
NotificationChannel = Literal["webhook", "email", "wecom", "feishu"]
NotificationEvent = Literal[
    "product_new",
    "variant_new",
    "price_change",
    "availability_change",
    "description_change",
    "text_change",
]


class SiteCreate(BaseModel):
    name: str = Field(default="", max_length=120)
    url: str = Field(min_length=3, max_length=500)
    category: str | None = Field(default=None, max_length=120)
    priority: int = Field(default=2, ge=1, le=3)
    notes: str | None = Field(default=None, max_length=1000)
    scan_interval_minutes: int = Field(default=60, ge=10, le=1440)
    webhook_url: str | None = Field(default=None, max_length=1000)
    notification_events: list[NotificationEvent] = Field(default_factory=lambda: ["product_new"])
    include_keywords: str | None = Field(default=None, max_length=500)
    exclude_keywords: str | None = Field(default=None, max_length=500)


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    priority: int | None = Field(default=None, ge=1, le=3)
    notes: str | None = Field(default=None, max_length=1000)
    scan_interval_minutes: int | None = Field(default=None, ge=10, le=1440)
    webhook_url: str | None = Field(default=None, max_length=1000)
    notification_events: list[NotificationEvent] | None = None
    enabled: bool | None = None


class SourceCreate(BaseModel):
    source_type: SourceType = "listing_page"
    url: str = Field(min_length=3, max_length=500)
    selector: str | None = Field(default=None, max_length=500)
    include_keywords: str | None = Field(default=None, max_length=500)
    exclude_keywords: str | None = Field(default=None, max_length=500)
    scan_interval_minutes: int = Field(default=60, ge=10, le=1440)


class SourceUpdate(BaseModel):
    selector: str | None = Field(default=None, max_length=500)
    include_keywords: str | None = Field(default=None, max_length=500)
    exclude_keywords: str | None = Field(default=None, max_length=500)
    scan_interval_minutes: int | None = Field(default=None, ge=10, le=1440)
    enabled: bool | None = None


class NotificationRuleCreate(BaseModel):
    site_id: int | None = None
    name: str = Field(default="通知策略", min_length=1, max_length=120)
    channel: NotificationChannel = "webhook"
    target_url: str = Field(min_length=3, max_length=1000)
    event_types: list[NotificationEvent] = Field(default_factory=lambda: ["product_new"])
    min_severity: SeverityLevel = "normal"
    inbox_status: InboxStatus = "unread"
    enabled: bool = True


class InboxStatusUpdate(BaseModel):
    inbox_status: Literal["unread", "read", "important", "follow_up", "archived", "false_positive"]
    assignee: str | None = Field(default=None, max_length=120)
    review_note: str | None = Field(default=None, max_length=1000)
    false_positive_reason: str | None = Field(default=None, max_length=500)


class EventSuppressionCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class UserCredentials(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)


@app.on_event("startup")
async def startup() -> None:
    init_db()
    runtime = runtime_settings()
    queue_backend = queue_backend_name()
    if runtime.start_background_workers and queue_backend == "in_process":
        asyncio.create_task(scan_worker_loop())
        asyncio.create_task(scheduler_loop())
    if runtime.start_background_workers and runtime.start_notification_worker:
        asyncio.create_task(notification_worker_loop())


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/system/health")
async def system_health(user: dict = CurrentUser) -> dict:
    settings = database_settings()
    queue = queue_settings()
    runtime = runtime_settings()
    return {
        "ok": True,
        "database_backend": settings.backend,
        "queue_configured_backend": queue.backend,
        "queue_backend": queue_backend_name(),
        "redis_configured": bool(queue.redis_url),
        "background_workers_enabled": runtime.start_background_workers,
        "notification_worker_enabled": runtime.start_background_workers and runtime.start_notification_worker,
        "sqlite_path": str(settings.sqlite_path) if settings.sqlite_path else None,
    }


@app.get("/api/system/ping")
async def system_ping() -> dict:
    return {"ok": True}


def parse_observability_time(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify_scan_failure(message: str | None) -> str:
    text = (message or "").lower()
    if "403" in text or "forbidden" in text or "access denied" in text or "blocked" in text:
        return "access_denied"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "render" in text or "playwright" in text:
        return "render_failed"
    if "selector" in text or "field missing" in text:
        return "field_missing"
    if "404" in text or "not found" in text:
        return "not_found"
    return "unknown"


@app.get("/api/operations/summary")
async def operations_summary(user: dict = CurrentUser) -> dict:
    with get_db() as db:
        scan_rows = fetchall(
            db,
            """
            SELECT scan_logs.status, scan_logs.started_at, scan_logs.finished_at, scan_logs.message
            FROM scan_logs
            JOIN sites ON sites.id = scan_logs.site_id
            WHERE sites.user_id = ?
            ORDER BY scan_logs.started_at DESC, scan_logs.id DESC
            LIMIT 100
            """,
            (user["id"],),
        )
        job_rows = fetchall(
            db,
            """
            SELECT scan_jobs.status
            FROM scan_jobs
            JOIN sites ON sites.id = scan_jobs.site_id
            WHERE sites.user_id = ?
            """,
            (user["id"],),
        )
        notification_rows = fetchall(
            db,
            """
            SELECT notification_outbox.status
            FROM notification_outbox
            JOIN sites ON sites.id = notification_outbox.site_id
            WHERE sites.user_id = ?
            """,
            (user["id"],),
        )

    scans = [row_to_dict(row) for row in scan_rows]
    successful = sum(1 for row in scans if row["status"] == "success")
    failed_rows = [row for row in scans if row["status"] != "success"]
    durations = []
    for row in scans:
        started_at = parse_observability_time(row.get("started_at"))
        finished_at = parse_observability_time(row.get("finished_at"))
        if started_at and finished_at:
            durations.append(round((finished_at - started_at).total_seconds() * 1000))
    categories: dict[str, int] = {}
    for row in failed_rows:
        category = classify_scan_failure(row.get("message"))
        categories[category] = categories.get(category, 0) + 1

    job_statuses = [row_to_dict(row).get("status") for row in job_rows]
    notification_statuses = [row_to_dict(row).get("status") for row in notification_rows]
    return {
        "scans": {
            "total": len(scans),
            "successful": successful,
            "failed": len(failed_rows),
            "success_rate": round(successful / len(scans), 4) if scans else None,
            "average_duration_ms": round(sum(durations) / len(durations)) if durations else None,
        },
        "queue": {
            "queued": sum(1 for status in job_statuses if status == "queued"),
            "running": sum(1 for status in job_statuses if status == "running"),
            "failed": sum(1 for status in job_statuses if status == "failed"),
        },
        "notifications": {
            "pending": sum(1 for status in notification_statuses if status == "pending"),
            "sending": sum(1 for status in notification_statuses if status == "sending"),
            "failed": sum(1 for status in notification_statuses if status == "failed"),
        },
        "failure_categories": [
            {"category": category, "count": count}
            for category, count in sorted(categories.items(), key=lambda item: (-item[1], item[0]))
        ],
    }


def load_sources_by_site() -> dict[int, list[dict]]:
    with get_db() as db:
        rows = fetchall(
            db,
            "SELECT * FROM monitor_sources ORDER BY site_id, id"
        )
    sources: dict[int, list[dict]] = {}
    for row in rows:
        data = row_to_dict(row)
        sources.setdefault(data["site_id"], []).append(data)
    return sources


def enrich_product(row) -> dict:
    product = row_to_dict(row)
    product["display_url"] = product.get("url")
    if product.get("item_type") == "product_detail":
        product["link_label"] = "查看产品"
    else:
        product["link_label"] = "查看来源页"
    return product


def enrich_change_event(row) -> dict:
    return row_to_dict(row)


def snapshot_detail(db, snapshot_id: int | None) -> dict | None:
    if not snapshot_id:
        return None
    row = fetchone(db, "SELECT * FROM source_snapshots WHERE id = ?", (snapshot_id,))
    if not row:
        return None
    detail = row_to_dict(row)
    if detail.get("screenshot_path"):
        detail["screenshot_url"] = f"/api/source-snapshots/{detail['id']}/screenshot"
    else:
        detail["screenshot_url"] = None
    detail.pop("screenshot_path", None)
    return detail


@app.get("/api/source-snapshots/{snapshot_id}/screenshot")
async def get_snapshot_screenshot(snapshot_id: int, user: dict = CurrentUser):
    with get_db() as db:
        snapshot = fetchone(
            db,
            """
            SELECT source_snapshots.screenshot_path
            FROM source_snapshots
            JOIN monitor_sources ON monitor_sources.id = source_snapshots.source_id
            JOIN sites ON sites.id = monitor_sources.site_id
            WHERE source_snapshots.id = ? AND sites.user_id = ?
            """,
            (snapshot_id, user["id"]),
        )
    if not snapshot or not snapshot["screenshot_path"]:
        raise HTTPException(status_code=404, detail="Screenshot evidence not found")
    try:
        screenshot_file = evidence_path(snapshot["screenshot_path"])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Screenshot evidence not found") from exc
    if not screenshot_file.is_file():
        raise HTTPException(status_code=404, detail="Screenshot evidence not found")
    return FileResponse(screenshot_file, media_type="image/png")


def csv_response(filename: str, fieldnames: list[str], rows: list[dict]) -> Response:
    stream = io.StringIO()
    stream.write("\ufeff")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def write_audit_log(
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    site_id: int | None = None,
    source_id: int | None = None,
    summary: str | None = None,
    metadata: dict | None = None,
) -> None:
    with get_db() as db:
        insert_row(
            db,
            "audit_logs",
            {
                "user_id": user_id,
                "site_id": site_id,
                "source_id": source_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "action": action,
                "summary": summary,
                "metadata": json_dumps(metadata or {}),
            },
        )


def ensure_site_owner(site_id: int, user_id: int) -> None:
    with get_db() as db:
        site = fetchone(
            db,
            "SELECT id FROM sites WHERE id = ? AND user_id = ?",
            (site_id, user_id),
        )
    if not site:
        raise HTTPException(status_code=404, detail="品牌档案不存在")


def ensure_source_owner(source_id: int, user_id: int) -> None:
    with get_db() as db:
        source = fetchone(
            db,
            """
            SELECT monitor_sources.id
            FROM monitor_sources
            JOIN sites ON sites.id = monitor_sources.site_id
            WHERE monitor_sources.id = ? AND sites.user_id = ?
            """,
            (source_id, user_id),
        )
    if not source:
        raise HTTPException(status_code=404, detail="监控源不存在")


@app.post("/api/auth/register")
async def register(payload: UserCredentials, response: Response) -> dict:
    email = normalize_email(payload.email)
    with get_db() as db:
        exists = fetchone(db, "SELECT id FROM users WHERE email = ?", (email,))
        if exists:
            raise HTTPException(status_code=400, detail="这个邮箱已经注册")
        user_id = insert_row(
            db,
            "users",
            {
                "email": email,
                "password_hash": hash_password(payload.password),
            },
        )
        user = select_by_id(db, "users", user_id)
    session = create_session(user["id"])
    set_session_cookie(response, session)
    return {"user": public_user(user), **session}


@app.post("/api/auth/login")
async def login(payload: UserCredentials, response: Response) -> dict:
    email = normalize_email(payload.email)
    check_login_rate_limit(email)
    with get_db() as db:
        user = fetchone(db, "SELECT * FROM users WHERE email = ?", (email,))
        if not user or not verify_password(payload.password, user["password_hash"]):
            record_failed_login(email)
            raise HTTPException(status_code=400, detail="邮箱或密码不正确")
        execute_sql(db, "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
    clear_failed_login(email)
    session = create_session(user["id"])
    set_session_cookie(response, session)
    return {"user": public_user(user), **session}


@app.get("/api/auth/me")
async def me(user: dict = CurrentUser) -> dict:
    return user


@app.post("/api/auth/logout")
async def logout(response: Response, authorization: str | None = Header(default=None)) -> dict:
    if authorization:
        _, _, token = authorization.partition(" ")
        if token:
            revoke_session_token(token)
    clear_session_cookie(response)
    return {"ok": True}


@app.get("/api/sites")
async def list_sites(user: dict = CurrentUser) -> list[dict]:
    with get_db() as db:
        rows = fetchall(
            db,
            "SELECT * FROM sites WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        )
    sources = load_sources_by_site()
    sites = []
    for row in rows:
        site = row_to_dict(row)
        site["sources"] = sources.get(site["id"], [])
        sites.append(site)
    return sites


@app.post("/api/sites")
async def add_site(payload: SiteCreate, user: dict = CurrentUser) -> dict:
    try:
        site = create_site(
            user["id"],
            payload.name,
            payload.url,
            payload.scan_interval_minutes,
            payload.webhook_url,
            payload.notification_events,
            payload.category,
            payload.priority,
            payload.notes,
            payload.include_keywords,
            payload.exclude_keywords,
        )
        write_audit_log(
            user["id"],
            "site.create" if not site.get("already_exists") else "site.reuse",
            "site",
            entity_id=site.get("id"),
            site_id=site.get("id"),
            summary=f"Added site {site.get('name') or site.get('url')}",
            metadata={"url": site.get("url"), "already_exists": bool(site.get("already_exists"))},
        )
        return site
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/sites/{site_id}")
async def update_site(site_id: int, payload: SiteUpdate, user: dict = CurrentUser) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新字段")
    if "notification_events" in updates:
        updates["notification_events"] = json_dumps(updates.pop("notification_events") or ["product_new"])
    if updates.get("webhook_url"):
        try:
            updates["webhook_url"] = validate_public_http_url(updates["webhook_url"])
        except UnsafeUrlError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    clauses = assignment_list(list(updates.keys()))
    with get_db() as db:
        values = list(updates.values()) + [site_id, user["id"]]
        execute_sql(db, f"UPDATE sites SET {clauses} WHERE id = ? AND user_id = ?", values)
        site = fetchone(
            db,
            "SELECT * FROM sites WHERE id = ? AND user_id = ?",
            (site_id, user["id"]),
        )
    if not site:
        raise HTTPException(status_code=404, detail="品牌档案不存在")
    write_audit_log(
        user["id"],
        "site.update",
        "site",
        entity_id=site_id,
        site_id=site_id,
        summary=f"Updated site {site['name'] or site['url']}",
        metadata={"fields": sorted(updates.keys())},
    )
    return row_to_dict(site)


@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: int, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        site = fetchone(db, "SELECT * FROM sites WHERE id = ? AND user_id = ?", (site_id, user["id"]))
    if site:
        write_audit_log(
            user["id"],
            "site.delete",
            "site",
            entity_id=site_id,
            site_id=site_id,
            summary=f"Deleted site {site['name'] or site['url']}",
            metadata={"url": site["url"]},
        )
        with get_db() as db:
            execute_sql(db, "DELETE FROM sites WHERE id = ? AND user_id = ?", (site_id, user["id"]))
    return {"ok": True}


@app.post("/api/sites/{site_id}/sources")
async def add_source(site_id: int, payload: SourceCreate, user: dict = CurrentUser) -> dict:
    ensure_site_owner(site_id, user["id"])
    try:
        source = create_source(
            site_id,
            payload.source_type,
            payload.url,
            payload.scan_interval_minutes,
            payload.include_keywords,
            payload.exclude_keywords,
            payload.selector,
        )
        write_audit_log(
            user["id"],
            "source.create",
            "source",
            entity_id=source.get("id"),
            site_id=site_id,
            source_id=source.get("id"),
            summary=f"Added source {source.get('source_type')} for site {site_id}",
            metadata={"url": source.get("url"), "source_type": source.get("source_type")},
        )
        return source
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/sources/{source_id}")
async def update_source(source_id: int, payload: SourceUpdate, user: dict = CurrentUser) -> dict:
    ensure_source_owner(source_id, user["id"])
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新字段")
    with get_db() as db:
        update_by_id(db, "monitor_sources", source_id, updates)
        source = fetchone(db, "SELECT * FROM monitor_sources WHERE id = ?", (source_id,))
    if not source:
        raise HTTPException(status_code=404, detail="监控源不存在")
    write_audit_log(
        user["id"],
        "source.update",
        "source",
        entity_id=source_id,
        site_id=source["site_id"],
        source_id=source_id,
        summary=f"Updated source {source['source_type']} for site {source['site_id']}",
        metadata={"fields": sorted(updates.keys())},
    )
    return row_to_dict(source)


@app.delete("/api/sources/{source_id}")
async def delete_source(source_id: int, user: dict = CurrentUser) -> dict:
    ensure_source_owner(source_id, user["id"])
    with get_db() as db:
        source = fetchone(db, "SELECT * FROM monitor_sources WHERE id = ?", (source_id,))
    if source:
        write_audit_log(
            user["id"],
            "source.delete",
            "source",
            entity_id=source_id,
            site_id=source["site_id"],
            source_id=source_id,
            summary=f"Deleted source {source['source_type']} for site {source['site_id']}",
            metadata={"url": source["url"], "source_type": source["source_type"]},
        )
        with get_db() as db:
            execute_sql(db, "DELETE FROM monitor_sources WHERE id = ?", (source_id,))
    return {"ok": True}


@app.patch("/api/products/{product_id}/inbox-status")
async def update_product_inbox_status(product_id: int, payload: InboxStatusUpdate, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        execute_sql(
            db,
            """
            UPDATE products
            SET inbox_status = ?
            WHERE id = ?
              AND site_id IN (SELECT id FROM sites WHERE user_id = ?)
            """,
            (payload.inbox_status, product_id, user["id"]),
        )
        product = fetchone(
            db,
            """
            SELECT products.*
            FROM products
            JOIN sites ON sites.id = products.site_id
            WHERE products.id = ? AND sites.user_id = ?
            """,
            (product_id, user["id"]),
        )
    if not product:
        raise HTTPException(status_code=404, detail="新品记录不存在")
    return row_to_dict(product)


@app.get("/api/products/{product_id}/variants")
async def list_product_variants(product_id: int, user: dict = CurrentUser) -> list[dict]:
    with get_db() as db:
        product = fetchone(
            db,
            """
            SELECT products.id
            FROM products
            JOIN sites ON sites.id = products.site_id
            WHERE products.id = ? AND sites.user_id = ?
            """,
            (product_id, user["id"]),
        )
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")
        rows = fetchall(
            db,
            """
            SELECT * FROM product_variants
            WHERE product_id = ?
            ORDER BY is_active DESC, availability = 'in_stock' DESC, price_amount ASC, id ASC
            """,
            (product_id,),
        )
    return [row_to_dict(row) for row in rows]


@app.get("/api/products/{product_id}/matches")
async def list_product_matches(product_id: int, user: dict = CurrentUser) -> list[dict]:
    with get_db() as db:
        owned_product = fetchone(
            db,
            """
            SELECT products.id
            FROM products
            JOIN sites ON sites.id = products.site_id
            WHERE products.id = ? AND sites.user_id = ?
            """,
            (product_id, user["id"]),
        )
        if not owned_product:
            raise HTTPException(status_code=404, detail="Product not found")
        rows = fetchall(
            db,
            """
            SELECT
                product_match_groups.id AS group_id,
                product_match_groups.identifier_type,
                product_match_groups.normalized_value AS identifier_value,
                products.id AS product_id,
                products.title AS product_title,
                products.url AS product_url,
                products.price,
                products.price_amount,
                products.currency,
                products.availability,
                sites.id AS site_id,
                sites.name AS site_name
            FROM product_match_members own_members
            JOIN product_match_groups ON product_match_groups.id = own_members.group_id
            JOIN product_match_members group_members ON group_members.group_id = product_match_groups.id
            JOIN products ON products.id = group_members.product_id
            JOIN sites ON sites.id = products.site_id
            WHERE own_members.product_id = ?
              AND product_match_groups.user_id = ?
            ORDER BY product_match_groups.id, sites.name, products.id
            """,
            (product_id, user["id"]),
        )
    groups: dict[int, dict] = {}
    for row in rows:
        group_id = row["group_id"]
        group = groups.setdefault(
            group_id,
            {"id": group_id, "identifier_type": row["identifier_type"], "identifier_value": row["identifier_value"], "products": []},
        )
        group["products"].append(
            {
                "id": row["product_id"],
                "title": row["product_title"],
                "url": row["product_url"],
                "price": row["price"],
                "price_amount": row["price_amount"],
                "currency": row["currency"],
                "availability": row["availability"],
                "site_id": row["site_id"],
                "site_name": row["site_name"],
            }
        )
    return list(groups.values())


@app.get("/api/product-match-groups")
async def list_product_match_groups(user: dict = CurrentUser) -> list[dict]:
    """Return only exact, cross-site identity matches owned by the current user."""
    with get_db() as db:
        rows = fetchall(
            db,
            """
            SELECT
                product_match_groups.id AS group_id,
                product_match_groups.identifier_type,
                product_match_groups.normalized_value AS identifier_value,
                products.id AS product_id,
                products.title AS product_title,
                products.url AS product_url,
                products.price,
                products.price_amount,
                products.currency,
                products.availability,
                sites.id AS site_id,
                sites.name AS site_name
            FROM product_match_groups
            JOIN product_match_members ON product_match_members.group_id = product_match_groups.id
            JOIN products ON products.id = product_match_members.product_id
            JOIN sites ON sites.id = products.site_id
            WHERE product_match_groups.user_id = ?
            ORDER BY product_match_groups.id DESC, sites.name, products.id
            """,
            (user["id"],),
        )
    groups: dict[int, dict] = {}
    for row in rows:
        group_id = row["group_id"]
        group = groups.setdefault(
            group_id,
            {
                "id": group_id,
                "identifier_type": row["identifier_type"],
                "identifier_value": row["identifier_value"],
                "products": [],
            },
        )
        group["products"].append(
            {
                "id": row["product_id"],
                "title": row["product_title"],
                "url": row["product_url"],
                "price": row["price"],
                "price_amount": row["price_amount"],
                "currency": row["currency"],
                "availability": row["availability"],
                "site_id": row["site_id"],
                "site_name": row["site_name"],
            }
        )
    return list(groups.values())


@app.patch("/api/change-events/{event_id}/inbox-status")
async def update_change_event_inbox_status(event_id: int, payload: InboxStatusUpdate, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        execute_sql(
            db,
            """
            UPDATE change_events
            SET inbox_status = ?,
                assignee = ?,
                review_note = ?,
                false_positive_reason = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
              AND site_id IN (SELECT id FROM sites WHERE user_id = ?)
            """,
            (
                payload.inbox_status,
                payload.assignee,
                payload.review_note,
                payload.false_positive_reason,
                event_id,
                user["id"],
            ),
        )
        event = fetchone(
            db,
            """
            SELECT change_events.*
            FROM change_events
            JOIN sites ON sites.id = change_events.site_id
            WHERE change_events.id = ? AND sites.user_id = ?
            """,
            (event_id, user["id"]),
        )
    if not event:
        raise HTTPException(status_code=404, detail="变化事件不存在")
    return row_to_dict(event)


@app.get("/api/event-suppression-rules")
async def list_event_suppression_rules(user: dict = CurrentUser) -> list[dict]:
    with get_db() as db:
        rows = fetchall(
            db,
            """
            SELECT event_suppression_rules.*, sites.name AS site_name, monitor_sources.url AS source_url
            FROM event_suppression_rules
            JOIN sites ON sites.id = event_suppression_rules.site_id
            JOIN monitor_sources ON monitor_sources.id = event_suppression_rules.source_id
            WHERE sites.user_id = ?
            ORDER BY event_suppression_rules.created_at DESC, event_suppression_rules.id DESC
            """,
            (user["id"],),
        )
    return [row_to_dict(row) for row in rows]


@app.post("/api/change-events/{event_id}/suppress-similar")
async def suppress_similar_change_events(event_id: int, payload: EventSuppressionCreate, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        event = fetchone(
            db,
            """
            SELECT change_events.id, change_events.site_id, change_events.source_id, change_events.change_type
            FROM change_events
            JOIN sites ON sites.id = change_events.site_id
            WHERE change_events.id = ? AND sites.user_id = ?
            """,
            (event_id, user["id"]),
        )
        if not event:
            raise HTTPException(status_code=404, detail="Change event not found")
        existing = fetchone(
            db,
            "SELECT * FROM event_suppression_rules WHERE source_id = ? AND change_type = ?",
            (event["source_id"], event["change_type"]),
        )
        if existing:
            update_by_id(db, "event_suppression_rules", existing["id"], {"reason": payload.reason, "enabled": True})
            rule = fetchone(db, "SELECT * FROM event_suppression_rules WHERE id = ?", (existing["id"],))
        else:
            rule_id = insert_row(
                db,
                "event_suppression_rules",
                {
                    "site_id": event["site_id"],
                    "source_id": event["source_id"],
                    "change_type": event["change_type"],
                    "reason": payload.reason,
                    "enabled": True,
                },
            )
            rule = fetchone(db, "SELECT * FROM event_suppression_rules WHERE id = ?", (rule_id,))
    return row_to_dict(rule)


@app.post("/api/sites/{site_id}/scan")
async def trigger_scan(site_id: int, user: dict = CurrentUser) -> dict:
    ensure_site_owner(site_id, user["id"])
    try:
        job = await enqueue_site_scan(site_id, trigger_type="manual")
        write_audit_log(
            user["id"],
            "scan.site",
            "site",
            entity_id=site_id,
            site_id=site_id,
            summary=f"Queued site scan {site_id}",
            metadata={"job_id": job.get("id"), "status": job.get("status")},
        )
        return job
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/sources/{source_id}/scan")
async def trigger_source_scan(source_id: int, user: dict = CurrentUser) -> dict:
    ensure_source_owner(source_id, user["id"])
    with get_db() as db:
        source = fetchone(db, "SELECT site_id FROM monitor_sources WHERE id = ?", (source_id,))
    try:
        job = await enqueue_source_scan(source_id, trigger_type="manual")
        write_audit_log(
            user["id"],
            "scan.source",
            "source",
            entity_id=source_id,
            site_id=source["site_id"] if source else job.get("site_id"),
            source_id=source_id,
            summary=f"Queued source scan {source_id}",
            metadata={"job_id": job.get("id"), "status": job.get("status")},
        )
        return job
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/products")
async def list_products(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            products.*,
            sites.name AS site_name,
            monitor_sources.source_type AS source_type
        FROM products
        JOIN sites ON sites.id = products.site_id
        LEFT JOIN monitor_sources ON monitor_sources.id = products.source_id
    """
    params: list[int] = []
    sql += " WHERE sites.user_id = ?"
    params.append(user["id"])
    if site_id:
        sql += " AND products.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY products.detected_at DESC LIMIT 200"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    return [enrich_product(row) for row in rows]


@app.get("/api/export/products.csv")
async def export_products_csv(site_id: int | None = None, user: dict = CurrentUser) -> Response:
    sql = """
        SELECT
            products.*,
            sites.name AS site_name,
            monitor_sources.source_type AS source_type
        FROM products
        JOIN sites ON sites.id = products.site_id
        LEFT JOIN monitor_sources ON monitor_sources.id = products.source_id
        WHERE sites.user_id = ?
    """
    params: list[int] = [user["id"]]
    if site_id:
        sql += " AND products.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY products.detected_at DESC LIMIT 5000"

    with get_db() as db:
        rows = fetchall(db, sql, params)

    export_rows = []
    for row in rows:
        product = enrich_product(row)
        export_rows.append(
            {
                "site_name": product.get("site_name") or "",
                "title": product.get("title") or "",
                "url": product.get("url") or "",
                "price": product.get("price") or "",
                "price_amount": product.get("price_amount") or "",
                "currency": product.get("currency") or "",
                "compare_at_price": product.get("compare_at_price") or "",
                "availability": product.get("availability") or "",
                "variant_count": product.get("variant_count") or "",
                "status": product.get("discovery_status") or "",
                "inbox_status": product.get("inbox_status") or "",
                "review_status": product.get("review_status") or "",
                "source_type": product.get("source_type") or "",
                "extraction_source": product.get("extraction_source") or "",
                "confidence_score": product.get("confidence_score") or 0,
                "features": " | ".join(product.get("features") or []),
                "description": product.get("description") or "",
                "detected_at": product.get("detected_at") or "",
            }
        )
    return csv_response(
        "products.csv",
        [
            "site_name",
            "title",
            "url",
            "price",
            "price_amount",
            "currency",
            "compare_at_price",
            "availability",
            "variant_count",
            "status",
            "inbox_status",
            "review_status",
            "source_type",
            "extraction_source",
            "confidence_score",
            "features",
            "description",
            "detected_at",
        ],
        export_rows,
    )


@app.get("/api/scan-logs")
async def list_scan_logs(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            scan_logs.*,
            sites.name AS site_name,
            monitor_sources.source_type AS source_type,
            monitor_sources.url AS source_url
        FROM scan_logs
        JOIN sites ON sites.id = scan_logs.site_id
        LEFT JOIN monitor_sources ON monitor_sources.id = scan_logs.source_id
    """
    params: list[int] = []
    sql += " WHERE sites.user_id = ?"
    params.append(user["id"])
    if site_id:
        sql += " AND scan_logs.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY scan_logs.started_at DESC LIMIT 100"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    return [row_to_dict(row) for row in rows]


@app.get("/api/scan-jobs")
async def list_scan_jobs(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            scan_jobs.*,
            sites.name AS site_name,
            monitor_sources.source_type AS source_type,
            monitor_sources.url AS source_url
        FROM scan_jobs
        JOIN sites ON sites.id = scan_jobs.site_id
        LEFT JOIN monitor_sources ON monitor_sources.id = scan_jobs.source_id
    """
    params: list[int] = []
    sql += " WHERE sites.user_id = ?"
    params.append(user["id"])
    if site_id:
        sql += " AND scan_jobs.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY scan_jobs.queued_at DESC LIMIT 100"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    jobs = []
    for row in rows:
        jobs.append(row_to_dict(row))
    return jobs


@app.get("/api/audit-logs")
async def list_audit_logs(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            audit_logs.*,
            sites.name AS site_name,
            sites.url AS site_url,
            monitor_sources.source_type AS source_type,
            monitor_sources.url AS source_url
        FROM audit_logs
        LEFT JOIN sites ON sites.id = audit_logs.site_id
        LEFT JOIN monitor_sources ON monitor_sources.id = audit_logs.source_id
        WHERE audit_logs.user_id = ?
    """
    params: list[int] = [user["id"]]
    if site_id:
        sql += " AND audit_logs.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY audit_logs.created_at DESC LIMIT 200"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    logs = []
    for row in rows:
        logs.append(row_to_dict(row))
    return logs


def normalize_notification_rule(row: dict) -> dict:
    rule = row_to_dict(row)
    rule["enabled"] = bool(rule.get("enabled"))
    if not rule.get("event_types"):
        rule["event_types"] = ["product_new"]
    return rule


@app.get("/api/notification-rules")
async def list_notification_rules(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            notification_rules.*,
            sites.name AS site_name,
            sites.url AS site_url
        FROM notification_rules
        LEFT JOIN sites ON sites.id = notification_rules.site_id
        WHERE notification_rules.user_id = ?
    """
    params: list[int] = [user["id"]]
    if site_id:
        sql += " AND notification_rules.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY notification_rules.enabled DESC, notification_rules.created_at DESC"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    return [normalize_notification_rule(row) for row in rows]


@app.post("/api/notification-rules")
async def create_notification_rule(payload: NotificationRuleCreate, user: dict = CurrentUser) -> dict:
    if not payload.event_types:
        raise HTTPException(status_code=400, detail="通知规则至少需要一个事件类型")
    if payload.channel == "email":
        raise HTTPException(status_code=400, detail="邮件通道尚未接入真实发件服务，请使用 Webhook、企业微信或飞书")
    if payload.channel not in {"webhook", "wecom", "feishu"}:
        raise HTTPException(status_code=400, detail="不支持的通知通道")
    parsed_target = urlparse(payload.target_url)
    if parsed_target.scheme not in {"http", "https"} or not parsed_target.hostname:
        raise HTTPException(status_code=400, detail="机器人地址必须是有效的 HTTP(S) URL")
    target_url = payload.target_url

    with get_db() as db:
        if payload.site_id is not None:
            site = fetchone(db, "SELECT id FROM sites WHERE id = ? AND user_id = ?", (payload.site_id, user["id"]))
            if not site:
                raise HTTPException(status_code=404, detail="监控站点不存在")
        rule_id = insert_row(
            db,
            "notification_rules",
            {
                "user_id": user["id"],
                "site_id": payload.site_id,
                "name": payload.name,
                "channel": payload.channel,
                "target_url": target_url,
                "event_types": json_dumps(payload.event_types),
                "min_severity": payload.min_severity,
                "inbox_status": payload.inbox_status,
                "enabled": payload.enabled,
            },
        )
        row = fetchone(
            db,
            """
            SELECT
                notification_rules.*,
                sites.name AS site_name,
                sites.url AS site_url
            FROM notification_rules
            LEFT JOIN sites ON sites.id = notification_rules.site_id
            WHERE notification_rules.id = ? AND notification_rules.user_id = ?
            """,
            (rule_id, user["id"]),
        )

    write_audit_log(
        user["id"],
        "notification_rule.create",
        "notification_rule",
        entity_id=rule_id,
        site_id=payload.site_id,
        summary=f"Created notification rule {payload.name}",
        metadata={
            "channel": payload.channel,
            "event_types": payload.event_types,
            "min_severity": payload.min_severity,
            "inbox_status": payload.inbox_status,
        },
    )
    return normalize_notification_rule(row)


@app.get("/api/notifications")
async def list_notifications(site_id: int | None = None, user: dict = CurrentUser) -> list[dict]:
    sql = """
        SELECT
            notification_outbox.*,
            sites.name AS site_name,
            products.title AS product_title,
            products.url AS product_url,
            change_events.summary AS event_summary,
            change_events.change_type AS change_type
        FROM notification_outbox
        JOIN sites ON sites.id = notification_outbox.site_id
        LEFT JOIN products ON products.id = notification_outbox.product_id
        LEFT JOIN change_events ON change_events.id = notification_outbox.event_id
    """
    params: list[int] = []
    sql += " WHERE sites.user_id = ?"
    params.append(user["id"])
    if site_id:
        sql += " AND notification_outbox.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY notification_outbox.created_at DESC LIMIT 100"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    notifications = []
    for row in rows:
        notifications.append(row_to_dict(row))
    return notifications


@app.get("/api/export/notifications.csv")
async def export_notifications_csv(site_id: int | None = None, user: dict = CurrentUser) -> Response:
    sql = """
        SELECT
            notification_outbox.*,
            sites.name AS site_name,
            products.title AS product_title,
            products.url AS product_url,
            change_events.summary AS event_summary,
            change_events.change_type AS change_type
        FROM notification_outbox
        JOIN sites ON sites.id = notification_outbox.site_id
        LEFT JOIN products ON products.id = notification_outbox.product_id
        LEFT JOIN change_events ON change_events.id = notification_outbox.event_id
        WHERE sites.user_id = ?
    """
    params: list[int] = [user["id"]]
    if site_id:
        sql += " AND notification_outbox.site_id = ?"
        params.append(site_id)
    sql += " ORDER BY notification_outbox.created_at DESC LIMIT 5000"

    with get_db() as db:
        rows = fetchall(db, sql, params)

    export_rows = []
    for row in rows:
        item = row_to_dict(row)
        export_rows.append(
            {
                "site_name": item.get("site_name") or "",
                "product_title": item.get("product_title") or "",
                "product_url": item.get("product_url") or "",
                "event_type": item.get("event_type") or item.get("change_type") or "",
                "event_summary": item.get("event_summary") or "",
                "channel": item.get("channel") or "",
                "target_url": item.get("target_url") or "",
                "status": item.get("status") or "",
                "attempts": item.get("attempts") or 0,
                "max_attempts": item.get("max_attempts") or 0,
                "next_attempt_at": item.get("next_attempt_at") or "",
                "last_error": item.get("last_error") or "",
                "created_at": item.get("created_at") or "",
                "sent_at": item.get("sent_at") or "",
            }
        )
    return csv_response(
        "notifications.csv",
        [
            "site_name",
            "product_title",
            "product_url",
            "event_type",
            "event_summary",
            "channel",
            "target_url",
            "status",
            "attempts",
            "max_attempts",
            "next_attempt_at",
            "last_error",
            "created_at",
            "sent_at",
        ],
        export_rows,
    )


@app.post("/api/notifications/{notification_id}/retry")
async def retry_notification(notification_id: int, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        execute_sql(
            db,
            """
            UPDATE notification_outbox
            SET status = 'pending', attempts = 0, next_attempt_at = CURRENT_TIMESTAMP, last_error = NULL
            WHERE id = ?
              AND site_id IN (SELECT id FROM sites WHERE user_id = ?)
              AND status IN ('failed', 'pending')
            """,
            (notification_id, user["id"]),
        )
        row = fetchone(
            db,
            """
            SELECT notification_outbox.*
            FROM notification_outbox
            JOIN sites ON sites.id = notification_outbox.site_id
            WHERE notification_outbox.id = ? AND sites.user_id = ?
            """,
            (notification_id, user["id"]),
        )
    if not row:
        raise HTTPException(status_code=404, detail="通知记录不存在")
    write_audit_log(
        user["id"],
        "notification.retry",
        "notification",
        entity_id=notification_id,
        site_id=row["site_id"],
        summary=f"Retried notification {notification_id}",
        metadata={"status": row["status"], "attempts": row["attempts"]},
    )
    await process_pending_notifications(limit=5)
    with get_db() as db:
        refreshed = fetchone(
            db,
            """
            SELECT notification_outbox.*
            FROM notification_outbox
            JOIN sites ON sites.id = notification_outbox.site_id
            WHERE notification_outbox.id = ? AND sites.user_id = ?
            """,
            (notification_id, user["id"]),
        )
    return row_to_dict(refreshed or row)


@app.get("/api/change-events/{event_id}")
async def get_change_event(event_id: int, user: dict = CurrentUser) -> dict:
    with get_db() as db:
        row = fetchone(
            db,
            """
            SELECT
                change_events.*,
                sites.name AS site_name,
                sites.url AS site_url,
                monitor_sources.source_type AS source_type,
                monitor_sources.url AS source_url,
                monitor_sources.selector AS selector,
                products.title AS product_title,
                products.url AS product_url,
                products.price AS product_price,
                products.currency AS product_currency,
                products.availability AS product_availability
            FROM change_events
            JOIN sites ON sites.id = change_events.site_id
            JOIN monitor_sources ON monitor_sources.id = change_events.source_id
            LEFT JOIN products ON products.id = change_events.product_id
            WHERE change_events.id = ? AND sites.user_id = ?
            """,
            (event_id, user["id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Change event not found")

        detail = enrich_change_event(row)
        detail["snapshot_before"] = snapshot_detail(db, row["snapshot_before_id"])
        detail["snapshot_after"] = snapshot_detail(db, row["snapshot_after_id"])

        scan_row = fetchone(
            db,
            """
            SELECT
                scan_logs.*,
                sites.name AS site_name,
                monitor_sources.source_type AS source_type,
                monitor_sources.url AS source_url
            FROM scan_logs
            JOIN sites ON sites.id = scan_logs.site_id
            LEFT JOIN monitor_sources ON monitor_sources.id = scan_logs.source_id
            WHERE scan_logs.site_id = ?
              AND (scan_logs.source_id = ? OR scan_logs.source_id IS NULL)
            ORDER BY scan_logs.started_at DESC
            LIMIT 1
            """,
            (row["site_id"], row["source_id"]),
        )
        detail["scan_metadata"] = row_to_dict(scan_row) if scan_row else None
        return detail


@app.get("/api/change-events")
async def list_change_events(
    site_id: int | None = None,
    inbox_status: Literal["unread", "read", "important", "follow_up", "archived", "false_positive"] | None = None,
    assignee: str | None = None,
    change_type: str | None = None,
    severity: str | None = None,
    q: str | None = None,
    user: dict = CurrentUser,
) -> list[dict]:
    sql = """
        SELECT
            change_events.*,
            sites.name AS site_name,
            monitor_sources.source_type AS source_type,
            monitor_sources.url AS source_url,
            monitor_sources.selector AS selector,
            products.title AS product_title,
            products.url AS product_url
        FROM change_events
        JOIN sites ON sites.id = change_events.site_id
        JOIN monitor_sources ON monitor_sources.id = change_events.source_id
        LEFT JOIN products ON products.id = change_events.product_id
    """
    params: list[int] = []
    sql += " WHERE sites.user_id = ?"
    params.append(user["id"])
    if site_id:
        sql += " AND change_events.site_id = ?"
        params.append(site_id)
    if inbox_status:
        sql += " AND change_events.inbox_status = ?"
        params.append(inbox_status)
    if assignee:
        sql += " AND change_events.assignee = ?"
        params.append(assignee)
    if change_type:
        sql += " AND change_events.change_type = ?"
        params.append(change_type)
    if severity:
        sql += " AND change_events.severity = ?"
        params.append(severity)
    if q:
        like_query = f"%{q.strip()}%"
        sql += """
            AND (
                change_events.summary LIKE ?
                OR sites.name LIKE ?
                OR products.title LIKE ?
                OR monitor_sources.url LIKE ?
            )
        """
        params.extend([like_query, like_query, like_query, like_query])
    sql += " ORDER BY change_events.created_at DESC LIMIT 100"

    with get_db() as db:
        rows = fetchall(db, sql, params)
    return [enrich_change_event(row) for row in rows]
