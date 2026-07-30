from __future__ import annotations

import asyncio
import difflib
import json
from datetime import datetime, timedelta, timezone

from app.crawler import classify_product_url, discover_candidates, extract_candidate_product, extract_source_text, normalize_url
from app.db import DB_BACKEND, boolean_true_sql, execute_sql, fetchall, fetchone, get_db, insert_ignore, insert_row, is_integrity_error, json_dumps, row_to_dict, select_by_id, storage_column, update_by_id, update_by_id_when
from app.evidence_store import load_screenshot, save_screenshot
from app.notifier import change_event_payload, should_notify_event
from app.render_worker import try_render_page
from app.url_safety import validate_public_http_url
from app.visual_evidence import screenshot_hash, visual_change_ratio


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SITE_CREATED_STATUS = "宸叉坊鍔犲搧鐗屾。妗堬紝绛夊緟寤虹珛鍩虹嚎"
SOURCE_WAITING_BASELINE_STATUS = "绛夊緟寤虹珛鍩虹嚎"


def split_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    normalized = value.replace("\uff0c", ",").replace("\uff1b", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def source_scan_strategy(source_type: str) -> tuple[bool, bool]:
    if source_type == "homepage":
        return True, True
    if source_type in {"sitemap", "rss"}:
        return False, True
    return False, False


def create_scan_log(
    site_id: int,
    source_id: int | None,
    started_at: str,
    status: str,
    mode: str,
    candidates_count: int,
    new_count: int,
    message: str,
) -> None:
    with get_db() as db:
        insert_row(
            db,
            "scan_logs",
            {
                "site_id": site_id,
                "source_id": source_id,
                "started_at": started_at,
                "finished_at": now_iso(),
                "status": status,
                "mode": mode,
                "candidates_count": candidates_count,
                "new_count": new_count,
                "message": message,
            },
        )


def create_scan_job(
    site_id: int,
    source_id: int | None,
    job_type: str,
    trigger_type: str,
    parent_job_id: int | None = None,
) -> int:
    with get_db() as db:
        return insert_row(
            db,
            "scan_jobs",
            {
                "parent_job_id": parent_job_id,
                "site_id": site_id,
                "source_id": source_id,
                "job_type": job_type,
                "trigger_type": trigger_type,
                "status": "queued",
                "queued_at": now_iso(),
            },
        )


def claim_scan_job(job_id: int) -> bool:
    with get_db() as db:
        return bool(
            update_by_id_when(
                db,
                "scan_jobs",
                job_id,
                {"status": "running", "started_at": now_iso()},
                {"status": "queued"},
            )
        )


def mark_scan_job_running(job_id: int) -> None:
    claim_scan_job(job_id)


def finish_scan_job(
    job_id: int,
    status: str,
    candidates_count: int = 0,
    new_count: int = 0,
    error_count: int = 0,
    message: str = "",
    result: dict | None = None,
) -> None:
    with get_db() as db:
        update_by_id(
            db,
            "scan_jobs",
            job_id,
            {
                "status": status,
                "finished_at": now_iso(),
                "candidates_count": candidates_count,
                "new_count": new_count,
                "error_count": error_count,
                "message": message,
                "result": json_dumps(result or {}),
            },
        )


def update_source_status(source_id: int, status: str) -> None:
    with get_db() as db:
        update_by_id(db, "monitor_sources", source_id, {"last_checked_at": now_iso(), "last_status": status})


def mark_source_scan_success(source_id: int, status: str) -> None:
    with get_db() as db:
        update_by_id(
            db,
            "monitor_sources",
            source_id,
            {
                "last_checked_at": now_iso(),
                "last_status": status,
                "failure_count": 0,
                "next_scan_after": None,
            },
        )


def next_backoff_time(failure_count: int) -> str:
    minutes_by_failure = [5, 15, 45, 120, 360]
    minutes = minutes_by_failure[min(max(failure_count, 1), len(minutes_by_failure)) - 1]
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def mark_source_scan_failure(source_id: int, status: str) -> int:
    with get_db() as db:
        row = fetchone(
            db,
            "SELECT failure_count FROM monitor_sources WHERE id = ?",
            (source_id,),
        )
        failure_count = int(row["failure_count"] if row else 0) + 1
        update_by_id(
            db,
            "monitor_sources",
            source_id,
            {
                "last_checked_at": now_iso(),
                "last_status": status,
                "failure_count": failure_count,
                "next_scan_after": next_backoff_time(failure_count),
            },
        )
    return failure_count


def source_backoff_active(source_data: dict) -> bool:
    next_scan_after = source_data.get("next_scan_after")
    if not next_scan_after:
        return False
    try:
        return datetime.fromisoformat(next_scan_after) > datetime.now(timezone.utc)
    except ValueError:
        return False


def update_site_status(site_id: int, status: str) -> None:
    with get_db() as db:
        update_by_id(db, "sites", site_id, {"last_checked_at": now_iso(), "last_status": status})


def latest_snapshot_id(db, source_id: int) -> int | None:
    row = fetchone(
        db,
        """
        SELECT id FROM source_snapshots
        WHERE source_id = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (source_id,),
    )
    return row["id"] if row else None


def event_diff(field: str, before, after) -> list[dict]:
    return [{"type": "changed", "field": field, "before": before, "after": after}]


def is_event_suppressed(db, source_id: int, change_type: str) -> bool:
    row = fetchone(
        db,
        """
        SELECT enabled FROM event_suppression_rules
        WHERE source_id = ? AND change_type = ?
        """,
        (source_id, change_type),
    )
    return bool(row and row["enabled"])


def insert_product_change_event(
    db,
    *,
    site_id: int,
    source_id: int,
    product_id: int | None,
    snapshot_id: int,
    change_type: str,
    severity: str,
    summary: str,
    diff: list[dict],
    snapshot_before_id: int | None = None,
) -> int | None:
    if is_event_suppressed(db, source_id, change_type):
        return None
    return insert_row(
        db,
        "change_events",
        {
            "site_id": site_id,
            "source_id": source_id,
            "product_id": product_id,
            "snapshot_before_id": snapshot_before_id,
            "snapshot_after_id": snapshot_id,
            "change_type": change_type,
            "severity": severity,
            "summary": summary,
            "diff": json_dumps(diff),
        },
    )


def enqueue_event_notification_if_enabled(
    db,
    site: dict,
    *,
    event_id: int | None,
    event_type: str,
    product_id: int | None,
    event: dict,
    product: dict | None,
) -> None:
    if event_id is None:
        return
    if site.get("_notify_enabled") is False:
        return
    event_row = fetchone(db, "SELECT severity, inbox_status FROM change_events WHERE id = ?", (event_id,))
    event_severity = str(event.get("severity") or (event_row["severity"] if event_row else "normal") or "normal")
    event_inbox_status = str((event_row["inbox_status"] if event_row else "unread") or "unread")
    severity_rank = {"low": 0, "normal": 1, "high": 2, "critical": 3}
    matching_rules = fetchall(
        db,
        """
        SELECT notification_rules.*
        FROM notification_rules
        JOIN sites ON sites.user_id = notification_rules.user_id
        WHERE notification_rules.enabled = 1
          AND sites.id = ?
          AND (notification_rules.site_id = ? OR notification_rules.site_id IS NULL)
        """,
        (site["site_id"], site["site_id"]),
    )
    matched_rule = False
    for raw_rule in matching_rules:
        rule = row_to_dict(raw_rule)
        if rule.get("channel") not in {"webhook", "wecom", "feishu"}:
            continue
        if event_type not in set(rule.get("event_types") or []):
            continue
        if severity_rank.get(event_severity, 1) < severity_rank.get(str(rule.get("min_severity") or "normal"), 1):
            continue
        if str(rule.get("inbox_status") or "unread") != event_inbox_status:
            continue
        safe_target_url = validate_public_http_url(rule["target_url"])
        payload = change_event_payload(event, product)
        insert_ignore(
            db,
            "notification_outbox",
            ["site_id", "product_id", "event_id", "event_type", "channel", "target_url", "payload", "status", "next_attempt_at"],
            (
                site["site_id"],
                product_id,
                event_id,
                event_type,
                rule["channel"],
                safe_target_url,
                json_dumps(payload),
                "pending",
                now_iso(),
            ),
        )
        matched_rule = True
    if matched_rule:
        return
    if not should_notify_event(site, event_type):
        return
    webhook_url = site.get("webhook_url")
    if not webhook_url:
        return
    safe_webhook_url = validate_public_http_url(webhook_url)
    payload = change_event_payload(event, product)
    insert_ignore(
        db,
        "notification_outbox",
        ["site_id", "product_id", "event_id", "event_type", "channel", "target_url", "payload", "status", "next_attempt_at"],
        (
            site["site_id"],
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


def record_product_update_events(db, existing, product, source_data: dict, source_id: int) -> None:
    snapshot_id = latest_snapshot_id(db, source_id)
    if not snapshot_id:
        return
    product_id = existing["id"]
    title = product.title

    old_price_key = (existing["price_amount"], existing["currency"], existing["price"], existing["compare_at_price"])
    new_price_key = (product.price_amount, product.currency, product.price, product.compare_at_price)
    if old_price_key != new_price_key:
        diff = event_diff("price", existing["price"] or existing["price_amount"], product.price or product.price_amount)
        summary = f"\u4ef7\u683c\u53d8\u5316\uff1a{title}"
        event_id = insert_product_change_event(
            db,
            site_id=source_data["site_id"],
            source_id=source_id,
            product_id=product_id,
            snapshot_id=snapshot_id,
            change_type="price_change",
            severity="high",
            summary=summary,
            diff=diff,
        )
        enqueue_event_notification_if_enabled(
            db,
            source_data,
            event_id=event_id,
            event_type="price_change",
            product_id=product_id,
            event={"id": event_id, "change_type": "price_change", "summary": summary, "diff": diff},
            product={"id": product_id, "title": title, "url": product.url, "price": product.price},
        )

    if (existing["availability"] or "") != (product.availability or ""):
        diff = event_diff("availability", existing["availability"], product.availability)
        summary = f"搴撳瓨鐘舵€佸彉鍖栵細{title}"
        event_id = insert_product_change_event(
            db,
            site_id=source_data["site_id"],
            source_id=source_id,
            product_id=product_id,
            snapshot_id=snapshot_id,
            change_type="availability_change",
            severity="high",
            summary=summary,
            diff=diff,
        )
        enqueue_event_notification_if_enabled(
            db,
            source_data,
            event_id=event_id,
            event_type="availability_change",
            product_id=product_id,
            event={"id": event_id, "change_type": "availability_change", "summary": summary, "diff": diff},
            product={"id": product_id, "title": title, "url": product.url, "availability": product.availability},
        )

    if (existing["description"] or "") != (product.description or ""):
        diff_items, added, removed = create_text_diff(existing["description"] or "", product.description or "", limit=12)
        diff = diff_items or event_diff("description", existing["description"], product.description)
        summary = f"\u4ea7\u54c1\u63cf\u8ff0\u53d8\u5316\uff1a{title}"
        event_id = insert_product_change_event(
            db,
            site_id=source_data["site_id"],
            source_id=source_id,
            product_id=product_id,
            snapshot_id=snapshot_id,
            change_type="description_change",
            severity="normal" if added + removed < 8 else "high",
            summary=summary,
            diff=diff,
        )
        enqueue_event_notification_if_enabled(
            db,
            source_data,
            event_id=event_id,
            event_type="description_change",
            product_id=product_id,
            event={"id": event_id, "change_type": "description_change", "summary": summary, "diff": diff},
            product={"id": product_id, "title": title, "url": product.url},
        )


def record_new_product_event(db, saved: dict, source_data: dict, source_id: int) -> None:
    snapshot_id = latest_snapshot_id(db, source_id)
    if not snapshot_id:
        return
    diff = [
        {"type": "added", "field": "title", "text": saved["title"]},
        {"type": "added", "field": "url", "text": saved["url"]},
    ]
    summary = f"\u65b0\u589e\u4ea7\u54c1\uff1a{saved['title']}"
    event_id = insert_product_change_event(
        db,
        site_id=source_data["site_id"],
        source_id=source_id,
        product_id=saved["id"],
        snapshot_id=snapshot_id,
        change_type="product_new",
        severity="high",
        summary=summary,
        diff=diff,
    )
    enqueue_event_notification_if_enabled(
        db,
        source_data,
        event_id=event_id,
        event_type="product_new",
        product_id=saved["id"],
        event={"id": event_id, "change_type": "product_new", "summary": summary, "diff": diff},
        product=saved,
    )


def sync_product_variants(
    db,
    product_id: int,
    product,
    source_data: dict | None = None,
    source_id: int | None = None,
    record_changes: bool = False,
) -> None:
    existing_rows = fetchall(db, "SELECT * FROM product_variants WHERE product_id = ?", (product_id,))
    existing_by_external_id = {row["external_id"]: row for row in existing_rows}
    snapshot_id = latest_snapshot_id(db, source_id) if record_changes and source_id else None
    seen_external_ids: set[str] = set()
    for variant in product.variants:
        seen_external_ids.add(variant.external_id)
        values = {
            "sku": variant.sku,
            "title": variant.title,
            "option_values": " / ".join(variant.option_values),
            "price": variant.price,
            "price_amount": variant.price_amount,
            "compare_at_price": variant.compare_at_price,
            "availability": variant.availability,
            "is_active": True,
            "last_seen_at": now_iso(),
        }
        existing = existing_by_external_id.get(variant.external_id)
        if existing:
            if snapshot_id and source_data:
                variant_label = variant.sku or variant.title or variant.external_id
                old_price_key = (existing["price_amount"], existing["price"], existing["compare_at_price"])
                new_price_key = (variant.price_amount, variant.price, variant.compare_at_price)
                if old_price_key != new_price_key:
                    diff = event_diff("variant_price", existing["price"] or existing["price_amount"], variant.price or variant.price_amount)
                    diff[0].update({"variant_external_id": variant.external_id, "variant_sku": variant.sku, "variant_title": variant.title})
                    summary = f"变体价格变化：{product.title} · {variant_label}"
                    event_id = insert_product_change_event(
                        db,
                        site_id=source_data["site_id"],
                        source_id=source_id,
                        product_id=product_id,
                        snapshot_id=snapshot_id,
                        change_type="price_change",
                        severity="high",
                        summary=summary,
                        diff=diff,
                    )
                    enqueue_event_notification_if_enabled(
                        db,
                        source_data,
                        event_id=event_id,
                        event_type="price_change",
                        product_id=product_id,
                        event={"id": event_id, "change_type": "price_change", "summary": summary, "diff": diff},
                        product={"id": product_id, "title": product.title, "url": product.url, "price": variant.price},
                    )
                if (existing["availability"] or "") != (variant.availability or ""):
                    diff = event_diff("variant_availability", existing["availability"], variant.availability)
                    diff[0].update({"variant_external_id": variant.external_id, "variant_sku": variant.sku, "variant_title": variant.title})
                    summary = f"变体库存变化：{product.title} · {variant_label}"
                    event_id = insert_product_change_event(
                        db,
                        site_id=source_data["site_id"],
                        source_id=source_id,
                        product_id=product_id,
                        snapshot_id=snapshot_id,
                        change_type="availability_change",
                        severity="high",
                        summary=summary,
                        diff=diff,
                    )
                    enqueue_event_notification_if_enabled(
                        db,
                        source_data,
                        event_id=event_id,
                        event_type="availability_change",
                        product_id=product_id,
                        event={"id": event_id, "change_type": "availability_change", "summary": summary, "diff": diff},
                        product={"id": product_id, "title": product.title, "url": product.url, "availability": variant.availability},
                    )
            update_by_id(db, "product_variants", existing["id"], values)
            continue
        insert_row(
            db,
            "product_variants",
            {
                "product_id": product_id,
                "external_id": variant.external_id,
                **values,
                "first_seen_at": now_iso(),
            },
        )
        if existing_rows and snapshot_id and source_data:
            variant_label = variant.sku or variant.title or variant.external_id
            diff = event_diff("variant_added", None, variant_label)
            diff[0].update({"variant_external_id": variant.external_id, "variant_sku": variant.sku, "variant_title": variant.title})
            summary = f"新增变体：{product.title} · {variant_label}"
            event_id = insert_product_change_event(
                db,
                site_id=source_data["site_id"],
                source_id=source_id,
                product_id=product_id,
                snapshot_id=snapshot_id,
                change_type="variant_new",
                severity="high",
                summary=summary,
                diff=diff,
            )
            enqueue_event_notification_if_enabled(
                db,
                source_data,
                event_id=event_id,
                event_type="variant_new",
                product_id=product_id,
                event={"id": event_id, "change_type": "variant_new", "summary": summary, "diff": diff},
                product={"id": product_id, "title": product.title, "url": product.url, "price": variant.price},
            )

    # Only complete Shopify payloads are authoritative enough to mark a
    # historical color or size as removed. Generic HTML/JSON-LD parsing may
    # omit variants entirely and must not deactivate stored records.
    if product.extraction_source != "shopify_api" or not product.variants:
        return
    for existing in existing_rows:
        if not existing["is_active"] or existing["external_id"] in seen_external_ids:
            continue
        variant_label = existing["sku"] or existing["title"] or existing["external_id"]
        if snapshot_id and source_data:
            diff = event_diff("variant_removed", variant_label, None)
            diff[0].update({"variant_external_id": existing["external_id"], "variant_sku": existing["sku"], "variant_title": existing["title"]})
            summary = f"变体下架：{product.title} · {variant_label}"
            event_id = insert_product_change_event(
                db,
                site_id=source_data["site_id"],
                source_id=source_id,
                product_id=product_id,
                snapshot_id=snapshot_id,
                change_type="availability_change",
                severity="high",
                summary=summary,
                diff=diff,
            )
            enqueue_event_notification_if_enabled(
                db,
                source_data,
                event_id=event_id,
                event_type="availability_change",
                product_id=product_id,
                event={"id": event_id, "change_type": "availability_change", "summary": summary, "diff": diff},
                product={"id": product_id, "title": product.title, "url": product.url, "availability": "unavailable"},
            )
        update_by_id(db, "product_variants", existing["id"], {"is_active": False, "availability": "unavailable"})


async def extract_and_store_product(
    candidate,
    source_data: dict,
    source_id: int,
    discovery_status: str,
    notify: bool,
    record_changes: bool = True,
) -> dict | None:
    candidate_url = normalize_url(candidate.url)
    item_type, review_status = classify_product_url(candidate_url)
    if item_type != "product_detail":
        return None

    product = await extract_candidate_product(candidate)
    if not product:
        return None

    product_url = normalize_url(product.url)
    item_type, review_status = classify_product_url(product_url)
    if item_type == "product_detail" and product.confidence_score < 0.7:
        review_status = "needs_review"
    event_source_data = {**source_data, "_notify_enabled": notify}
    with get_db() as db:
        exists = fetchone(
            db,
            "SELECT * FROM products WHERE site_id = ? AND url = ?",
            (source_data["site_id"], product_url),
        )
        if exists:
            if record_changes:
                record_product_update_events(db, exists, product, event_source_data, source_id)
            update_by_id(
                db,
                "products",
                exists["id"],
                {
                    "source_id": exists["source_id"] or source_id,
                    "title": product.title,
                    "description": product.description,
                    "image_url": product.image_url,
                    "price": product.price,
                    "price_amount": product.price_amount,
                    "currency": product.currency,
                    "compare_at_price": product.compare_at_price,
                    "availability": product.availability,
                    "variant_count": product.variant_count,
                    "item_type": item_type,
                    "review_status": review_status,
                    "extraction_source": product.extraction_source,
                    "confidence_score": product.confidence_score,
                    "field_confidence": json_dumps(product.field_confidence),
                    "confidence_reasons": json_dumps(product.confidence_reasons),
                    "features": json_dumps(product.features),
                    "content_hash": product.content_hash,
                    "raw_text": product.raw_text,
                },
            )
            sync_product_variants(db, exists["id"], product, event_source_data, source_id, record_changes)
            return None
        product_id = insert_row(
            db,
            "products",
            {
                "site_id": source_data["site_id"],
                "source_id": source_id,
                "url": product_url,
                "title": product.title,
                "description": product.description,
                "image_url": product.image_url,
                "price": product.price,
                "price_amount": product.price_amount,
                "currency": product.currency,
                "compare_at_price": product.compare_at_price,
                "availability": product.availability,
                "variant_count": product.variant_count,
                "item_type": item_type,
                "review_status": review_status,
                "discovery_status": discovery_status,
                "extraction_source": product.extraction_source,
                "confidence_score": product.confidence_score,
                "field_confidence": json_dumps(product.field_confidence),
                "confidence_reasons": json_dumps(product.confidence_reasons),
                "features": json_dumps(product.features),
                "content_hash": product.content_hash,
                "raw_text": product.raw_text,
            },
        )
        sync_product_variants(db, product_id, product)

    saved = {
        "id": product_id,
        "url": product_url,
        "title": product.title,
        "description": product.description,
        "image_url": product.image_url,
        "price": product.price,
        "price_amount": product.price_amount,
        "currency": product.currency,
        "compare_at_price": product.compare_at_price,
        "availability": product.availability,
        "variant_count": product.variant_count,
        "item_type": item_type,
        "review_status": review_status,
        "discovery_status": discovery_status,
        "extraction_source": product.extraction_source,
        "confidence_score": product.confidence_score,
        "field_confidence": product.field_confidence,
        "confidence_reasons": product.confidence_reasons,
        "features": product.features,
        "site_name": source_data["site_name"],
    }

    if record_changes and discovery_status == "new":
        with get_db() as db:
            record_new_product_event(db, saved, event_source_data, source_id)
    return saved


def create_text_diff(before: str, after: str, limit: int = 36) -> tuple[list[dict], int, int]:
    before_lines = [line.strip() for line in before.splitlines() if line.strip()]
    after_lines = [line.strip() for line in after.splitlines() if line.strip()]
    diff_items: list[dict] = []
    added = 0
    removed = 0
    for line in difflib.ndiff(before_lines, after_lines):
        if line.startswith("+ "):
            added += 1
            if len(diff_items) < limit:
                diff_items.append({"type": "added", "text": line[2:]})
        elif line.startswith("- "):
            removed += 1
            if len(diff_items) < limit:
                diff_items.append({"type": "removed", "text": line[2:]})
    return diff_items, added, removed


async def capture_source_snapshot(source_data: dict, baseline_mode: bool, notify: bool = True) -> dict | None:
    extracted = await extract_source_text(source_data["url"], source_data.get("selector"))
    if not extracted:
        return None

    rendered = await try_render_page(source_data["url"], source_data.get("selector"))
    screenshot_png = rendered.screenshot_png if rendered else None
    screenshot_error = None if screenshot_png else "render_unavailable"
    current_screenshot_hash = screenshot_hash(screenshot_png) if screenshot_png else None

    with get_db() as db:
        previous = fetchone(
            db,
            """
            SELECT * FROM source_snapshots
            WHERE source_id = ?
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (source_data["id"],),
        )
        previous_visual = fetchone(
            db,
            """
            SELECT * FROM source_snapshots
            WHERE source_id = ? AND screenshot_path IS NOT NULL
            ORDER BY fetched_at DESC, id DESC
            LIMIT 1
            """,
            (source_data["id"],),
        )
        text_changed = bool(previous and previous["text_hash"] != extracted.text_hash)
        visual_ratio = None
        visual_changed = False
        if screenshot_png and previous_visual:
            previous_png = load_screenshot(previous_visual["screenshot_path"])
            if previous_png is not None:
                visual_ratio = visual_change_ratio(previous_png, screenshot_png)
                visual_changed = previous_visual["screenshot_hash"] != current_screenshot_hash
        snapshot_id = insert_row(
            db,
            "source_snapshots",
            {
                "source_id": source_data["id"],
                "url": extracted.url,
                "selector": extracted.selector,
                "fetched_at": now_iso(),
                "content_hash": extracted.content_hash,
                "text_hash": extracted.text_hash,
                "extracted_text": extracted.text,
                "capture_method": extracted.capture_method,
                "http_status": extracted.http_status,
                "content_type": extracted.content_type,
                "content_length": extracted.content_length,
                "screenshot_hash": current_screenshot_hash,
                "visual_change_ratio": visual_ratio,
                "screenshot_error": screenshot_error,
            },
        )

        screenshot_saved = False
        if screenshot_png and (baseline_mode or not previous_visual or text_changed or visual_changed):
            screenshot_path = save_screenshot(source_data["id"], snapshot_id, screenshot_png)
            update_by_id(db, "source_snapshots", snapshot_id, {"screenshot_path": screenshot_path})
            screenshot_saved = True

        if (text_changed or visual_changed) and not baseline_mode:
            if text_changed:
                diff_items, added, removed = create_text_diff(previous["extracted_text"] or "", extracted.text)
                change_type = "text_change"
                severity = "normal" if added + removed < 20 else "high"
                summary = f"\u9875\u9762\u6587\u672c\u53d1\u751f\u53d8\u5316\uff1a\u65b0\u589e {added} \u5904\uff0c\u5220\u9664 {removed} \u5904"
            else:
                diff_items = [
                    {
                        "type": "visual_change",
                        "before": previous_visual["screenshot_hash"],
                        "after": current_screenshot_hash,
                        "visual_change_ratio": visual_ratio,
                    }
                ]
                change_type = "visual_change"
                severity = "normal"
                summary = f"\u9875\u9762\u89c6\u89c9\u53d1\u751f\u53d8\u5316\uff1a\u50cf\u7d20\u53d8\u5316 {(visual_ratio or 0) * 100:.1f}%"
            event_id = insert_product_change_event(
                db,
                site_id=source_data["site_id"],
                source_id=source_data["id"],
                product_id=None,
                snapshot_id=snapshot_id,
                snapshot_before_id=previous["id"] if text_changed else previous_visual["id"],
                change_type=change_type,
                severity=severity,
                summary=summary,
                diff=diff_items,
            )
            if text_changed:
                enqueue_event_notification_if_enabled(
                    db,
                    {**source_data, "_notify_enabled": notify},
                    event_id=event_id,
                    event_type="text_change",
                    product_id=None,
                    event={"id": event_id, "change_type": "text_change", "summary": summary, "source_url": source_data["url"], "diff": diff_items},
                    product=None,
                )
            return {
                "snapshot_id": snapshot_id,
                "changed": True,
                "suppressed": event_id is None,
                "summary": summary,
                "screenshot_saved": screenshot_saved,
                "visual_change_ratio": visual_ratio,
            }
        return {
            "snapshot_id": snapshot_id,
            "changed": False,
            "screenshot_saved": screenshot_saved,
            "visual_change_ratio": visual_ratio,
        }


async def scan_source(
    source_id: int,
    notify: bool = True,
    trigger_type: str = "manual",
    parent_job_id: int | None = None,
    job_id: int | None = None,
) -> dict:
    started_at = now_iso()
    notification_events_column = storage_column("notification_events")
    with get_db() as db:
        source = fetchone(
            db,
            f"""
            SELECT
                monitor_sources.*,
                sites.name AS site_name,
                sites.webhook_url AS webhook_url,
                sites.{notification_events_column} AS {notification_events_column},
                sites.enabled AS site_enabled
            FROM monitor_sources
            JOIN sites ON sites.id = monitor_sources.site_id
            WHERE monitor_sources.id = ?
            """,
            (source_id,),
        )

    if not source:
        raise ValueError("鐩戞帶婧愪笉瀛樺湪")

    source_data = row_to_dict(source)
    if job_id is None:
        job_id = create_scan_job(
            source_data["site_id"],
            source_id,
            "source_scan",
            trigger_type,
            parent_job_id,
        )
    if not claim_scan_job(job_id):
        return {"site_id": source_data["site_id"], "source_id": source_id, "job_id": job_id, "status": "skipped"}
    if not source_data["enabled"] or not source_data["site_enabled"]:
        finish_scan_job(job_id, "failed", error_count=1, message="鐩戞帶婧愭湭鍚敤")
        raise ValueError("鐩戞帶婧愭湭鍚敤")

    use_sitemap, require_relevance = source_scan_strategy(source_data["source_type"])
    include_keywords = split_keywords(source_data.get("include_keywords"))
    exclude_keywords = split_keywords(source_data.get("exclude_keywords"))

    try:
        candidates = await discover_candidates(
            source_data["url"],
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            use_sitemap=use_sitemap,
            require_relevance=require_relevance,
            selector=source_data.get("selector"),
        )

        baseline_mode = not source_data.get("baseline_completed_at")
        product_baseline_mode = not source_data.get("product_baseline_completed_at")
        snapshot_result = await capture_source_snapshot(source_data, baseline_mode, notify=notify)
        inserted = []

        with get_db() as db:
            known_rows = fetchall(
                db,
                "SELECT url FROM known_urls WHERE source_id = ?",
                (source_id,),
            )
            known_urls = {row["url"] for row in known_rows}
            existing_product_count = fetchone(
                db,
                "SELECT COUNT(*) AS count FROM products WHERE source_id = ?",
                (source_id,),
            )["count"]
            backfill_as_baseline = existing_product_count == 0

        if baseline_mode or product_baseline_mode:
            baseline_products = []
            with get_db() as db:
                for candidate in candidates:
                    insert_ignore(
                        db,
                        "known_urls",
                        ["source_id", "url", "title_hint"],
                        (source_id, candidate.url, candidate.title_hint),
                    )
            for candidate in candidates:
                saved = await extract_and_store_product(
                    candidate,
                    source_data,
                    source_id,
                    "baseline",
                    notify=False,
                    record_changes=False,
                )
                if saved:
                    baseline_products.append(saved)
            with get_db() as db:
                total_products = fetchone(
                    db,
                    """
                    SELECT COUNT(*) AS count
                    FROM products
                    WHERE site_id = ?
                      AND item_type = 'product_detail'
                      AND review_status != 'false_positive'
                    """,
                    (source_data["site_id"],),
                )["count"]
                status = f"\u4ea7\u54c1\u5e93\u57fa\u7ebf\u5b8c\u6210\uff1a\u8bb0\u5f55 {len(candidates)} \u4e2a\u94fe\u63a5\uff0c\u5f53\u524d\u5171 {total_products} \u4e2a\u4ea7\u54c1\uff0c\u672c\u6b21\u8865\u5165 {len(baseline_products)} \u4e2a"
                execute_sql(
                    db,
                    """
                    UPDATE monitor_sources
                        SET
                        baseline_completed_at = COALESCE(baseline_completed_at, ?),
                        product_baseline_completed_at = ?,
                        last_checked_at = ?,
                        last_status = ?,
                        failure_count = 0,
                        next_scan_after = NULL
                    WHERE id = ?
                    """,
                    (
                        now_iso(),
                        now_iso(),
                        now_iso(),
                        status,
                        source_id,
                    ),
                )
            update_site_status(source_data["site_id"], status)
            mode = "baseline" if baseline_mode else "product_baseline"
            create_scan_log(
                source_data["site_id"],
                source_id,
                started_at,
                "success",
                mode,
                len(candidates),
                0,
                status,
            )
            result = {
                "site_id": source_data["site_id"],
                "source_id": source_id,
                "job_id": job_id,
                "mode": mode,
                "checked": len(candidates),
                "snapshot": snapshot_result,
                "baseline_products": baseline_products,
                "new_products": [],
            }
            finish_scan_job(
                job_id,
                "success",
                candidates_count=len(candidates),
                new_count=0,
                message=status,
                result=result,
            )
            return result

        for candidate in candidates:
            is_new_url = candidate.url not in known_urls
            with get_db() as db:
                insert_ignore(
                    db,
                    "known_urls",
                    ["source_id", "url", "title_hint"],
                    (source_id, candidate.url, candidate.title_hint),
                )
                execute_sql(
                    db,
                    "UPDATE known_urls SET last_seen_at = ? WHERE source_id = ? AND url = ?",
                    (now_iso(), source_id, candidate.url),
                )
            if not is_new_url:
                discovery_status = "baseline"
            elif backfill_as_baseline:
                discovery_status = "baseline"
            else:
                discovery_status = "new"

            saved = await extract_and_store_product(
                candidate,
                source_data,
                source_id,
                discovery_status,
                notify=notify,
                record_changes=True,
            )
            if saved:
                inserted.append(saved)

        new_inserted = [item for item in inserted if item.get("discovery_status") == "new"]
        baseline_inserted = [item for item in inserted if item.get("discovery_status") == "baseline"]
        status = f"\u68c0\u67e5\u5b8c\u6210\uff1a\u65b0\u589e {len(new_inserted)} \u4e2a\u4ea7\u54c1\uff0c\u8865\u5168 {len(baseline_inserted)} \u4e2a\u57fa\u7ebf\u4ea7\u54c1"
        mark_source_scan_success(source_id, status)
        update_site_status(source_data["site_id"], status)
        create_scan_log(
            source_data["site_id"],
            source_id,
            started_at,
            "success",
            "scan",
            len(candidates),
            len(new_inserted),
            status,
        )
        result = {
            "site_id": source_data["site_id"],
            "source_id": source_id,
            "job_id": job_id,
            "mode": "scan",
            "checked": len(candidates),
            "snapshot": snapshot_result,
            "baseline_products": baseline_inserted,
            "new_products": new_inserted,
        }
        finish_scan_job(
            job_id,
            "success",
            candidates_count=len(candidates),
            new_count=len(new_inserted),
            message=status,
            result=result,
        )
        return result
    except Exception as exc:
        message = f"妫€鏌ュけ璐ワ細{exc}"
        failure_count = mark_source_scan_failure(source_id, message)
        update_site_status(source_data["site_id"], message)
        create_scan_log(
            source_data["site_id"],
            source_id,
            started_at,
            "failed",
            "scan",
            0,
            0,
            message,
        )
        finish_scan_job(job_id, "failed", error_count=1, message=f"{message}\uff1b\u8fde\u7eed\u5931\u8d25 {failure_count} \u6b21")
        raise


async def scan_site(site_id: int, notify: bool = True) -> dict:
    with get_db() as db:
        site = select_by_id(db, "sites", site_id)
        sources = fetchall(
            db,
            f"SELECT * FROM monitor_sources WHERE site_id = ? AND {boolean_true_sql(DB_BACKEND, 'enabled')} ORDER BY id",
            (site_id,),
        )
    if not site:
        raise ValueError("\u54c1\u724c\u6863\u6848\u4e0d\u5b58\u5728")

    results = []
    errors = []
    new_products = []
    checked = 0
    for source in sources:
        try:
            result = await scan_source(source["id"], notify=notify)
            results.append(result)
            checked += result["checked"]
            new_products.extend(result["new_products"])
        except Exception as exc:
            errors.append({"source_id": source["id"], "message": str(exc)})

    return {
        "site_id": site_id,
        "checked": checked,
        "new_products": new_products,
        "sources": results,
        "errors": errors,
    }


async def scan_site(site_id: int, notify: bool = True, trigger_type: str = "manual", job_id: int | None = None) -> dict:
    with get_db() as db:
        site = select_by_id(db, "sites", site_id)
        sources = fetchall(
            db,
            f"SELECT * FROM monitor_sources WHERE site_id = ? AND {boolean_true_sql(DB_BACKEND, 'enabled')} ORDER BY id",
            (site_id,),
        )
    if not site:
        raise ValueError("\u54c1\u724c\u6863\u6848\u4e0d\u5b58\u5728")

    if job_id is None:
        job_id = create_scan_job(site_id, None, "site_scan", trigger_type)
    if not claim_scan_job(job_id):
        return {
            "site_id": site_id,
            "job_id": job_id,
            "checked": 0,
            "new_products": [],
            "sources": [],
            "errors": [],
            "status": "skipped",
        }
    results = []
    errors = []
    new_products = []
    checked = 0
    for source in sources:
        try:
            result = await scan_source(
                source["id"],
                notify=notify,
                trigger_type=trigger_type,
                parent_job_id=job_id,
            )
            results.append(result)
            checked += result["checked"]
            new_products.extend(result["new_products"])
        except Exception as exc:
            errors.append({"source_id": source["id"], "message": str(exc)})

    status = "success"
    if errors and results:
        status = "partial"
    elif errors and not results:
        status = "failed"
    result = {
        "site_id": site_id,
        "job_id": job_id,
        "checked": checked,
        "new_products": new_products,
        "sources": results,
        "errors": errors,
    }
    finish_scan_job(
        job_id,
        status,
        candidates_count=checked,
        new_count=len(new_products),
        error_count=len(errors),
        message=f"\u626b\u63cf\u5b8c\u6210\uff1a{len(results)} \u4e2a\u91c7\u96c6\u6e90\u6210\u529f\uff0c{len(errors)} \u4e2a\u5931\u8d25",
        result=result,
    )
    return result


async def scheduler_loop() -> None:
    while True:
        with get_db() as db:
            sources = fetchall(
                db,
                """
                SELECT monitor_sources.*
                FROM monitor_sources
                JOIN sites ON sites.id = monitor_sources.site_id
                WHERE {boolean_true_sql(DB_BACKEND, 'monitor_sources.enabled')} AND {boolean_true_sql(DB_BACKEND, 'sites.enabled')}
                """
            )
        for source in sources:
            data = row_to_dict(source)
            last = data.get("last_checked_at")
            should_scan = not last
            if last:
                try:
                    last_dt = datetime.fromisoformat(last)
                    elapsed = datetime.now(timezone.utc) - last_dt
                    should_scan = elapsed.total_seconds() >= data["scan_interval_minutes"] * 60
                except ValueError:
                    should_scan = True
            if should_scan and source_backoff_active(data):
                should_scan = False
            if should_scan:
                try:
                    from app.task_queue import enqueue_source_scan

                    await enqueue_source_scan(data["id"], trigger_type="scheduled")
                except Exception:
                    pass
        await asyncio.sleep(60)


def create_site(
    user_id: int,
    name: str,
    url: str,
    interval: int,
    webhook_url: str | None,
    notification_events: list[str] | None = None,
    category: str | None = None,
    priority: int = 2,
    notes: str | None = None,
    include_keywords: str | None = None,
    exclude_keywords: str | None = None,
) -> dict:
    normalized = validate_public_http_url(url)
    safe_webhook_url = validate_public_http_url(webhook_url) if webhook_url else None
    with get_db() as db:
        existing = fetchone(
            db,
            "SELECT * FROM sites WHERE user_id = ? AND url = ?",
            (user_id, normalized),
        )
        if existing:
            site = row_to_dict(existing)
            site["already_exists"] = True
            return site

        site_id = insert_row(
            db,
            "sites",
            {
                "user_id": user_id,
                "name": name.strip() or normalized,
                "url": normalized,
                "scan_interval_minutes": interval,
                "webhook_url": safe_webhook_url,
                "notification_events": json_dumps(notification_events or ["product_new"]),
                "category": category or None,
                "priority": priority,
                "notes": notes or None,
                "last_checked_at": now_iso(),
                "last_status": SITE_CREATED_STATUS,
            },
        )
        insert_row(
            db,
            "monitor_sources",
            {
                "site_id": site_id,
                "source_type": "homepage",
                "url": normalized,
                "include_keywords": include_keywords or None,
                "exclude_keywords": exclude_keywords or None,
                "scan_interval_minutes": interval,
                "last_checked_at": now_iso(),
                "last_status": SOURCE_WAITING_BASELINE_STATUS,
            },
        )
        site = select_by_id(db, "sites", site_id)
    created = row_to_dict(site)
    created["already_exists"] = False
    return created


def create_source(
    site_id: int,
    source_type: str,
    url: str,
    interval: int,
    include_keywords: str | None = None,
    exclude_keywords: str | None = None,
    selector: str | None = None,
) -> dict:
    normalized = validate_public_http_url(url)
    with get_db() as db:
        site = select_by_id(db, "sites", site_id)
        if not site:
            raise ValueError("\u54c1\u724c\u6863\u6848\u4e0d\u5b58\u5728")
        try:
            source_id = insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": site_id,
                    "source_type": source_type,
                    "url": normalized,
                    "selector": selector or None,
                    "include_keywords": include_keywords or None,
                    "exclude_keywords": exclude_keywords or None,
                    "scan_interval_minutes": interval,
                    "last_checked_at": now_iso(),
                    "last_status": SOURCE_WAITING_BASELINE_STATUS,
                },
            )
        except Exception as exc:
            if is_integrity_error(exc):
                raise ValueError("\u8fd9\u4e2a\u76d1\u63a7\u6e90\u5df2\u7ecf\u5b58\u5728") from exc
            raise
        source = select_by_id(db, "monitor_sources", source_id)
    return row_to_dict(source)
