from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.crawler import CatalogDiscoveryResult, ExtractedProduct, ProductCandidate
from app.db import execute_sql, fetchall, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.main import app
from app.monitor import create_scan_job, scan_site


class BaselineScanProgressApiTests(unittest.TestCase):
    def test_owner_can_read_running_baseline_scan_progress(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"baseline-owner-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            registered = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            self.assertEqual(registered.status_code, 200, registered.text)
            headers = {"Authorization": f"Bearer {registered.json()['token']}"}
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": registered.json()["user"]["id"],
                        "name": "Baseline scan site",
                        "url": f"https://baseline-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new"]),
                    },
                )
                job_id = insert_row(
                    db,
                    "scan_jobs",
                    {
                        "site_id": site_id,
                        "job_type": "site_scan",
                        "trigger_type": "baseline",
                        "status": "running",
                        "result": json_dumps(
                            {
                                "progress": {
                                    "phase": "extracting_products",
                                    "discovered_count": 12,
                                    "processed_count": 5,
                                    "failed_count": 1,
                                    "product_count": 5,
                                }
                            }
                        ),
                    },
                )

            response = client.get(f"/api/scan-jobs/{job_id}", headers=headers)

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["result"]["progress"]["processed_count"], 5)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (owner_email,))

    def test_other_user_cannot_read_baseline_scan_progress(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"baseline-owner-{marker}@monitor.internal"
        other_email = f"baseline-other-{marker}@monitor.internal"
        owner_client = TestClient(app)
        other_client = TestClient(app)
        try:
            owner = owner_client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            other = other_client.post("/api/auth/register", json={"email": other_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(other.status_code, 200, other.text)
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": owner.json()["user"]["id"],
                        "name": "Private baseline scan site",
                        "url": f"https://private-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new"]),
                    },
                )
                job_id = insert_row(
                    db,
                    "scan_jobs",
                    {"site_id": site_id, "job_type": "site_scan", "trigger_type": "baseline", "status": "running"},
                )

            response = other_client.get(f"/api/scan-jobs/{job_id}", headers={"Authorization": f"Bearer {other.json()['token']}"})

            self.assertEqual(response.status_code, 404, response.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, other_email))


class BaselineScanProgressRuntimeTests(unittest.TestCase):
    def test_first_baseline_records_products_without_new_product_events(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"baseline-runtime-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            registered = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            self.assertEqual(registered.status_code, 200, registered.text)
            owner_id = registered.json()["user"]["id"]
            site_url = f"https://baseline-runtime-{marker}.example.com"
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": owner_id,
                        "name": "Baseline runtime site",
                        "url": site_url,
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new"]),
                    },
                )
                insert_row(
                    db,
                    "monitor_sources",
                    {
                        "site_id": site_id,
                        "source_type": "homepage",
                        "url": site_url,
                        "scan_interval_minutes": 60,
                    },
                )
            job_id = create_scan_job(site_id, None, "site_scan", "baseline")
            candidates = [
                ProductCandidate(url=f"{site_url}/products/first", title_hint="First product"),
                ProductCandidate(url=f"{site_url}/products/second", title_hint="Second product"),
            ]
            extracted_products = [
                ExtractedProduct(
                    url=candidate.url,
                    title=candidate.title_hint or "Product",
                    description="Baseline product",
                    image_url=None,
                    price="$19.99",
                    price_amount=19.99,
                    currency="USD",
                    compare_at_price=None,
                    availability="in_stock",
                    variant_count=1,
                    variants=[],
                    features=["Water resistant"],
                    extraction_source="test",
                    confidence_score=0.95,
                    field_confidence={"price": 1.0},
                    confidence_reasons=[],
                    content_hash=f"hash-{index}",
                    raw_text="Baseline product",
                )
                for index, candidate in enumerate(candidates)
            ]
            discovery = CatalogDiscoveryResult(
                candidates=candidates,
                reference_count=None,
                discovery_source_counts={"product_sitemap": 2},
                adapter_attempts=[],
            )

            with (
                patch("app.monitor.discover_catalog", new=AsyncMock(return_value=discovery)),
                patch("app.monitor.capture_source_snapshot", new=AsyncMock(return_value=None)),
                patch("app.monitor.extract_candidate_product", new=AsyncMock(side_effect=extracted_products)),
            ):
                result = asyncio.run(scan_site(site_id, notify=True, trigger_type="baseline", job_id=job_id))

            with get_db() as db:
                job = row_to_dict(fetchone(db, "SELECT * FROM scan_jobs WHERE id = ?", (job_id,)))
                events = fetchall(db, "SELECT * FROM change_events WHERE site_id = ?", (site_id,))

            self.assertEqual(result["checked"], 2)
            self.assertTrue(job["result"]["progress"]["baseline_completed"])
            self.assertEqual(job["result"]["progress"]["product_count"], 2)
            self.assertEqual(events, [])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (owner_email,))


if __name__ == "__main__":
    unittest.main()
