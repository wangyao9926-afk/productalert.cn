from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import DB_BACKEND, execute_sql, get_db, init_db
from app.main import app
from app.settings import queue_settings, runtime_settings


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def run_smoke_test() -> dict:
    init_db()

    marker = uuid4().hex
    email = f"api-smoke-{marker}@monitor.internal"
    password = "smoke-test-password"
    site_id: int | None = None
    source_id: int | None = None
    event_id: int | None = None

    client = TestClient(app)
    try:
        ping = client.get("/api/system/ping")
        assert_status(ping, 200, "public ping")
        if ping.json().get("ok") is not True:
            raise RuntimeError("public ping did not return ok=true")

        register = client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
        )
        assert_status(register, 200, "register")
        token = register.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        health = client.get("/api/system/health", headers=headers)
        assert_status(health, 200, "health")
        health_data = health.json()
        expected_queue = queue_settings().backend
        if health_data.get("queue_configured_backend") != expected_queue:
            raise RuntimeError(f"unexpected configured queue backend: {health_data.get('queue_configured_backend')}")
        if health_data.get("queue_backend") != expected_queue:
            raise RuntimeError(f"unexpected queue backend: {health_data.get('queue_backend')}")
        runtime = runtime_settings()
        expected_background_workers = runtime.start_background_workers
        expected_notification_worker = runtime.start_background_workers and runtime.start_notification_worker
        if health_data.get("background_workers_enabled") is not expected_background_workers:
            raise RuntimeError("background worker health did not match runtime settings")
        if health_data.get("notification_worker_enabled") is not expected_notification_worker:
            raise RuntimeError("notification worker health did not match runtime settings")

        site = client.post(
            "/api/sites",
            headers=headers,
            json={
                "name": "API Smoke Site",
                "url": f"https://1.1.1.1/{marker}",
                "scan_interval_minutes": 60,
                "notification_events": ["product_new"],
            },
        )
        assert_status(site, 200, "create site")
        site_data = site.json()
        site_id = site_data["id"]

        sites = client.get("/api/sites", headers=headers)
        assert_status(sites, 200, "list sites")
        if not any(item["id"] == site_id for item in sites.json()):
            raise RuntimeError("created site was not returned by list sites")

        updated_site = client.patch(
            f"/api/sites/{site_id}",
            headers=headers,
            json={
                "category": "Updated Category",
                "priority": 1,
                "scan_interval_minutes": 180,
                "include_keywords": "launch,new",
                "exclude_keywords": "sale",
                "notification_events": ["product_new", "price_change"],
            },
        )
        assert_status(updated_site, 200, "update site settings")
        refreshed_sites = client.get("/api/sites", headers=headers)
        assert_status(refreshed_sites, 200, "reload updated sites")
        refreshed_site = next((item for item in refreshed_sites.json() if item["id"] == site_id), None)
        if not refreshed_site:
            raise RuntimeError("updated site was not returned by list sites")
        expected_events = ["product_new", "price_change"]
        if refreshed_site.get("scan_interval_minutes") != 180:
            raise RuntimeError("updated site scan interval was not persisted")
        if refreshed_site.get("priority") != 1:
            raise RuntimeError("updated site priority was not persisted")
        if refreshed_site.get("notification_events") != expected_events:
            raise RuntimeError(f"updated notification events were not persisted: {refreshed_site.get('notification_events')}")

        source = client.post(
            f"/api/sites/{site_id}/sources",
            headers=headers,
            json={
                "source_type": "custom_page",
                "url": f"https://1.0.0.1/{marker}/source",
                "scan_interval_minutes": 60,
            },
        )
        assert_status(source, 200, "create source")
        source_data = source.json()
        source_id = source_data["id"]

        with get_db() as db:
            snapshot_sql = """
                INSERT INTO source_snapshots (source_id, url, content_hash, text_hash, extracted_text)
                VALUES (?, ?, ?, ?, ?)
                """
            if DB_BACKEND.name == "postgresql":
                snapshot_sql += " RETURNING id"
            cursor = execute_sql(
                db,
                snapshot_sql,
                (source_id, f"https://1.0.0.1/{marker}/source", f"hash-{marker}", f"text-{marker}", "old"),
            )
            snapshot_id = cursor.fetchone()["id"] if DB_BACKEND.name == "postgresql" else cursor.lastrowid
            event_sql = """
                INSERT INTO change_events (site_id, source_id, snapshot_after_id, change_type, severity, summary)
                VALUES (?, ?, ?, ?, ?, ?)
                """
            if DB_BACKEND.name == "postgresql":
                event_sql += " RETURNING id"
            event_cursor = execute_sql(
                db,
                event_sql,
                (site_id, source_id, snapshot_id, "text_change", "normal", "API smoke change event"),
            )
            event_id = event_cursor.fetchone()["id"] if DB_BACKEND.name == "postgresql" else event_cursor.lastrowid

        event_detail = client.get(f"/api/change-events/{event_id}", headers=headers)
        assert_status(event_detail, 200, "change event detail")
        event_detail_data = event_detail.json()
        if event_detail_data.get("id") != event_id:
            raise RuntimeError(f"change event detail returned wrong id: {event_detail_data}")
        if event_detail_data.get("snapshot_after", {}).get("extracted_text") != "old":
            raise RuntimeError(f"change event detail did not include snapshot_after: {event_detail_data}")
        if "scan_metadata" not in event_detail_data:
            raise RuntimeError(f"change event detail did not include scan_metadata: {event_detail_data}")

        updated_source = client.patch(
            f"/api/sources/{source_id}",
            headers=headers,
            json={
                "enabled": False,
                "scan_interval_minutes": 120,
                "include_keywords": "product",
                "exclude_keywords": "clearance",
            },
        )
        assert_status(updated_source, 200, "update source")
        refreshed_sources = client.get("/api/sites", headers=headers)
        assert_status(refreshed_sources, 200, "reload updated source")
        refreshed_source_site = next((item for item in refreshed_sources.json() if item["id"] == site_id), None)
        refreshed_source = next(
            (item for item in refreshed_source_site.get("sources", []) if item["id"] == source_id),
            None,
        ) if refreshed_source_site else None
        if not refreshed_source:
            raise RuntimeError("updated source was not returned by list sites")
        if refreshed_source.get("enabled") is not False:
            raise RuntimeError("updated source enabled state was not persisted")
        if refreshed_source.get("scan_interval_minutes") != 120:
            raise RuntimeError("updated source scan interval was not persisted")

        site_scan = client.post(f"/api/sites/{site_id}/scan", headers=headers)
        assert_status(site_scan, 200, "queue site scan")

        source_scan = client.post(f"/api/sources/{source_id}/scan", headers=headers)
        assert_status(source_scan, 200, "queue source scan")

        for status in ["important", "read", "false_positive"]:
            status_response = client.patch(
                f"/api/change-events/{event_id}/inbox-status",
                headers=headers,
                json={
                    "inbox_status": status,
                    "assignee": "ops-owner",
                    "review_note": f"review note for {status}",
                    "false_positive_reason": "non-core-field-change" if status == "false_positive" else None,
                },
            )
            assert_status(status_response, 200, f"update change event inbox status {status}")
            status_payload = status_response.json()
            if status_payload.get("inbox_status") != status:
                raise RuntimeError(f"change event inbox status was not persisted: {status_payload}")
            if status_payload.get("assignee") != "ops-owner":
                raise RuntimeError(f"change event assignee was not persisted: {status_payload}")
            if status_payload.get("review_note") != f"review note for {status}":
                raise RuntimeError(f"change event review note was not persisted: {status_payload}")
            if status == "false_positive" and status_payload.get("false_positive_reason") != "non-core-field-change":
                raise RuntimeError(f"change event false positive reason was not persisted: {status_payload}")

        filtered_events = client.get(
            f"/api/change-events?site_id={site_id}&inbox_status=false_positive&assignee=ops-owner&change_type=text_change",
            headers=headers,
        )
        assert_status(filtered_events, 200, "filtered change events")
        filtered_payload = filtered_events.json()
        if not any(item.get("id") == event_id for item in filtered_payload):
            raise RuntimeError(f"filtered change events did not include expected event: {filtered_payload}")

        excluded_events = client.get(
            f"/api/change-events?site_id={site_id}&inbox_status=read&assignee=ops-owner&change_type=text_change",
            headers=headers,
        )
        assert_status(excluded_events, 200, "excluded filtered change events")
        excluded_payload = excluded_events.json()
        if any(item.get("id") == event_id for item in excluded_payload):
            raise RuntimeError(f"filtered change events did not exclude mismatched inbox status: {excluded_payload}")

        search_filtered_events = client.get(
            f"/api/change-events?site_id={site_id}&severity=normal&q=smoke",
            headers=headers,
        )
        assert_status(search_filtered_events, 200, "severity and search filtered change events")
        search_payload = search_filtered_events.json()
        if not any(item.get("id") == event_id for item in search_payload):
            raise RuntimeError(f"severity/q filtered events did not include expected event: {search_payload}")

        search_excluded_events = client.get(
            f"/api/change-events?site_id={site_id}&severity=high&q=smoke",
            headers=headers,
        )
        assert_status(search_excluded_events, 200, "severity mismatch filtered change events")
        search_excluded_payload = search_excluded_events.json()
        if any(item.get("id") == event_id for item in search_excluded_payload):
            raise RuntimeError(f"severity filter did not exclude mismatched event: {search_excluded_payload}")

        notification_rule = client.post(
            "/api/notification-rules",
            headers=headers,
            json={
                "site_id": site_id,
                "name": "High priority launch and price alerts",
                "channel": "webhook",
                "target_url": "https://hooks.example.com/productalert",
                "event_types": ["product_new", "price_change"],
                "min_severity": "high",
                "inbox_status": "important",
                "enabled": True,
            },
        )
        assert_status(notification_rule, 200, "create notification rule")
        notification_rule_payload = notification_rule.json()
        if notification_rule_payload.get("event_types") != ["product_new", "price_change"]:
            raise RuntimeError(f"notification rule event types were not persisted: {notification_rule_payload}")
        if notification_rule_payload.get("min_severity") != "high":
            raise RuntimeError(f"notification rule min severity was not persisted: {notification_rule_payload}")
        if notification_rule_payload.get("inbox_status") != "important":
            raise RuntimeError(f"notification rule inbox status was not persisted: {notification_rule_payload}")

        notification_rules = client.get("/api/notification-rules", headers=headers)
        assert_status(notification_rules, 200, "list notification rules")
        notification_rules_payload = notification_rules.json()
        if not any(item.get("id") == notification_rule_payload.get("id") for item in notification_rules_payload):
            raise RuntimeError(f"created notification rule was not returned by list endpoint: {notification_rules_payload}")

        for path in [
            "/api/products",
            "/api/scan-logs",
            "/api/scan-jobs",
            "/api/audit-logs",
            "/api/notifications",
            "/api/change-events",
        ]:
            response = client.get(path, headers=headers)
            assert_status(response, 200, path)
            if not isinstance(response.json(), list):
                raise RuntimeError(f"{path} did not return a list")

        delete_source = client.delete(f"/api/sources/{source_id}", headers=headers)
        assert_status(delete_source, 200, "delete source")
        source_id = None

        delete_site = client.delete(f"/api/sites/{site_id}", headers=headers)
        assert_status(delete_site, 200, "delete site")
        site_id = None

        return {
            "backend": DB_BACKEND.name,
            "email": email,
            "site_job_id": site_scan.json().get("id"),
            "source_job_id": source_scan.json().get("id"),
        }
    finally:
        if source_id is not None:
            client.delete(f"/api/sources/{source_id}", headers=locals().get("headers", {}))
        if site_id is not None:
            client.delete(f"/api/sites/{site_id}", headers=locals().get("headers", {}))
        cleanup_user(email)


def main() -> None:
    result = run_smoke_test()
    print(
        "api smoke ok "
        f"backend={result['backend']} "
        f"site_job_id={result['site_job_id']} "
        f"source_job_id={result['source_job_id']}"
    )


if __name__ == "__main__":
    main()
