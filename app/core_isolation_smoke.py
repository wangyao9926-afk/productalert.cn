from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, fetchone, get_db, init_db, insert_row, json_dumps
from app.main import app
from app.notifier import now_iso


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def cleanup_user(email: str) -> None:
    with get_db() as db:
        execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def register_user(email: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "smoke-test-password"},
    )
    assert_status(response, 200, f"register {email}")
    token = response.json()["token"]
    return client, {"Authorization": f"Bearer {token}"}


def create_site(client: TestClient, headers: dict, marker: str) -> int:
    response = client.post(
        "/api/sites",
        headers=headers,
        json={
            "name": f"Core Isolation {marker}",
            "url": f"https://1.1.1.1/{marker}",
            "scan_interval_minutes": 60,
            "notification_events": ["product_new"],
        },
    )
    assert_status(response, 200, "create site")
    return int(response.json()["id"])


def first_source_id(site_id: int) -> int:
    with get_db() as db:
        row = fetchone(
            db,
            "SELECT id FROM monitor_sources WHERE site_id = ? ORDER BY id ASC LIMIT 1",
            (site_id,),
        )
    if row is None:
        raise RuntimeError("site did not create a monitor source")
    return int(row["id"])


def create_owner_records(site_id: int, source_id: int, marker: str) -> dict:
    now = now_iso()
    with get_db() as db:
        product_id = insert_row(
            db,
            "products",
            {
                "site_id": site_id,
                "source_id": source_id,
                "url": f"https://example.com/products/{marker}",
                "title": f"Owner Product {marker}",
                "description": f"Owner-only product {marker}",
                "content_hash": f"product-{marker}",
                "features": json_dumps([f"feature-{marker}"]),
            },
        )
        scan_log_id = insert_row(
            db,
            "scan_logs",
            {
                "site_id": site_id,
                "source_id": source_id,
                "started_at": now,
                "finished_at": now,
                "status": "success",
                "mode": "smoke",
                "message": f"owner scan log {marker}",
            },
        )
        scan_job_id = insert_row(
            db,
            "scan_jobs",
            {
                "site_id": site_id,
                "source_id": source_id,
                "job_type": "source_scan",
                "trigger_type": "manual",
                "status": "success",
                "queued_at": now,
                "started_at": now,
                "finished_at": now,
                "message": f"owner scan job {marker}",
                "result": json_dumps({"marker": marker}),
            },
        )
        snapshot_id = insert_row(
            db,
            "source_snapshots",
            {
                "source_id": source_id,
                "url": f"https://example.com/source/{marker}",
                "fetched_at": now,
                "content_hash": f"snapshot-{marker}",
                "text_hash": f"text-{marker}",
                "extracted_text": f"owner snapshot {marker}",
            },
        )
        change_event_id = insert_row(
            db,
            "change_events",
            {
                "site_id": site_id,
                "source_id": source_id,
                "product_id": product_id,
                "snapshot_after_id": snapshot_id,
                "change_type": "text_change",
                "summary": f"owner change event {marker}",
                "diff": json_dumps([{"marker": marker}]),
            },
        )
    return {
        "product_id": product_id,
        "scan_log_id": scan_log_id,
        "scan_job_id": scan_job_id,
        "change_event_id": change_event_id,
    }


def assert_missing(items: list[dict], row_id: int, label: str) -> None:
    if any(int(item["id"]) == row_id for item in items):
        raise RuntimeError(f"{label} leaked another user's record {row_id}")


def assert_present(items: list[dict], row_id: int, label: str) -> None:
    if not any(int(item["id"]) == row_id for item in items):
        raise RuntimeError(f"{label} did not include owner's record {row_id}")


def assert_export_clean(text: str, marker: str, label: str) -> None:
    if marker in text:
        raise RuntimeError(f"{label} leaked marker {marker}")


def run_smoke_test() -> dict:
    init_db()
    marker = uuid4().hex
    owner_email = f"core-owner-{marker}@monitor.internal"
    stranger_email = f"core-stranger-{marker}@monitor.internal"
    owner_site_id: int | None = None

    try:
        owner_client, owner_headers = register_user(owner_email)
        stranger_client, stranger_headers = register_user(stranger_email)
        owner_site_id = create_site(owner_client, owner_headers, marker)
        source_id = first_source_id(owner_site_id)
        records = create_owner_records(owner_site_id, source_id, marker)

        owner_sites = owner_client.get("/api/sites", headers=owner_headers)
        assert_status(owner_sites, 200, "owner list sites")
        assert_present(owner_sites.json(), owner_site_id, "owner sites")

        stranger_sites = stranger_client.get("/api/sites", headers=stranger_headers)
        assert_status(stranger_sites, 200, "stranger list sites")
        assert_missing(stranger_sites.json(), owner_site_id, "stranger sites")

        owner_products = owner_client.get("/api/products", headers=owner_headers)
        assert_status(owner_products, 200, "owner list products")
        assert_present(owner_products.json(), records["product_id"], "owner products")

        stranger_products = stranger_client.get("/api/products", headers=stranger_headers)
        assert_status(stranger_products, 200, "stranger list products")
        assert_missing(stranger_products.json(), records["product_id"], "stranger products")

        stranger_product_export = stranger_client.get("/api/export/products.csv", headers=stranger_headers)
        assert_status(stranger_product_export, 200, "stranger export products")
        assert_export_clean(stranger_product_export.text, marker, "stranger products export")

        stranger_scan_logs = stranger_client.get("/api/scan-logs", headers=stranger_headers)
        assert_status(stranger_scan_logs, 200, "stranger list scan logs")
        assert_missing(stranger_scan_logs.json(), records["scan_log_id"], "stranger scan logs")

        stranger_scan_jobs = stranger_client.get("/api/scan-jobs", headers=stranger_headers)
        assert_status(stranger_scan_jobs, 200, "stranger list scan jobs")
        assert_missing(stranger_scan_jobs.json(), records["scan_job_id"], "stranger scan jobs")

        stranger_change_events = stranger_client.get("/api/change-events", headers=stranger_headers)
        assert_status(stranger_change_events, 200, "stranger list change events")
        assert_missing(stranger_change_events.json(), records["change_event_id"], "stranger change events")

        product_patch = stranger_client.patch(
            f"/api/products/{records['product_id']}/inbox-status",
            headers=stranger_headers,
            json={"inbox_status": "read"},
        )
        assert_status(product_patch, 404, "stranger update product")

        change_event_patch = stranger_client.patch(
            f"/api/change-events/{records['change_event_id']}/inbox-status",
            headers=stranger_headers,
            json={"inbox_status": "read"},
        )
        assert_status(change_event_patch, 404, "stranger update change event")

        site_scan = stranger_client.post(f"/api/sites/{owner_site_id}/scan", headers=stranger_headers)
        assert_status(site_scan, 404, "stranger trigger site scan")

        return {
            "site_id": owner_site_id,
            "product_id": records["product_id"],
            "change_event_id": records["change_event_id"],
        }
    finally:
        if owner_site_id is not None:
            owner_client.delete(f"/api/sites/{owner_site_id}", headers=locals().get("owner_headers", {}))
        cleanup_user(owner_email)
        cleanup_user(stranger_email)


def main() -> None:
    result = run_smoke_test()
    print(
        "core isolation smoke ok "
        f"site_id={result['site_id']} "
        f"product_id={result['product_id']} "
        f"change_event_id={result['change_event_id']}"
    )


if __name__ == "__main__":
    main()
