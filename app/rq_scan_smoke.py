from __future__ import annotations

from uuid import uuid4

from app.rq_preflight import run_preflight
from app.rq_compat import rq_worker_class


def assert_status(response, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise RuntimeError(f"{label} failed: {response.status_code} {response.text}")


def run_smoke_test() -> dict:
    run_preflight(check_redis=True)

    from fastapi.testclient import TestClient
    from redis import Redis
    from rq import Queue, SimpleWorker

    from app.db import DB_BACKEND, execute_sql, get_db, init_db
    from app.main import app
    from app.settings import queue_settings

    init_db()

    marker = uuid4().hex
    email = f"rq-scan-smoke-{marker}@monitor.internal"
    password = "smoke-test-password"
    site_id: int | None = None
    source_id: int | None = None

    settings = queue_settings()
    connection = Redis.from_url(settings.redis_url)
    scan_queue = Queue("scan", connection=connection)
    scan_queue.empty()
    client = TestClient(app)

    try:
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
        if health_data.get("queue_backend") != "rq":
            raise RuntimeError(f"unexpected queue backend: {health_data.get('queue_backend')}")

        site = client.post(
            "/api/sites",
            headers=headers,
            json={
                "name": "RQ Scan Smoke Site",
                "url": f"https://1.1.1.1/{marker}",
                "scan_interval_minutes": 60,
                "notification_events": ["product_new"],
            },
        )
        assert_status(site, 200, "create site")
        site_id = site.json()["id"]

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
        source_id = source.json()["id"]

        disable_source = client.patch(
            f"/api/sources/{source_id}",
            headers=headers,
            json={"enabled": False},
        )
        assert_status(disable_source, 200, "disable source")

        queued = client.post(f"/api/sources/{source_id}/scan", headers=headers)
        assert_status(queued, 200, "queue source scan")
        scan_job_id = queued.json()["id"]

        worker_class = rq_worker_class(SimpleWorker)
        worker = worker_class([scan_queue], connection=connection)
        worker.work(burst=True)

        scan_jobs = client.get("/api/scan-jobs", headers=headers)
        assert_status(scan_jobs, 200, "list scan jobs")
        scan_job = next((item for item in scan_jobs.json() if item["id"] == scan_job_id), None)
        if not scan_job:
            raise RuntimeError("queued scan job was not returned by list scan jobs")
        if scan_job["status"] != "failed":
            raise RuntimeError(f"expected disabled source scan to fail, got {scan_job['status']}")
        if not scan_job.get("finished_at"):
            raise RuntimeError("scan job did not record finished_at")

        delete_source = client.delete(f"/api/sources/{source_id}", headers=headers)
        assert_status(delete_source, 200, "delete source")
        source_id = None

        delete_site = client.delete(f"/api/sites/{site_id}", headers=headers)
        assert_status(delete_site, 200, "delete site")
        site_id = None

        return {
            "backend": DB_BACKEND.name,
            "queue_backend": health_data["queue_backend"],
            "scan_job_id": scan_job_id,
            "scan_job_status": scan_job["status"],
        }
    finally:
        if source_id is not None:
            client.delete(f"/api/sources/{source_id}", headers=locals().get("headers", {}))
        if site_id is not None:
            client.delete(f"/api/sites/{site_id}", headers=locals().get("headers", {}))
        with get_db() as db:
            execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


def main() -> None:
    result = run_smoke_test()
    print(
        "rq scan smoke ok "
        f"backend={result['backend']} "
        f"queue_backend={result['queue_backend']} "
        f"scan_job_id={result['scan_job_id']} "
        f"status={result['scan_job_status']}"
    )


if __name__ == "__main__":
    main()
