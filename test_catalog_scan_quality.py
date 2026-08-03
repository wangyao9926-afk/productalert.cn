from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.crawler import ExtractedProduct, ProductCandidate, ProductFetchError, discover_product_candidates, fetch_result_from_response, raise_for_fetch_failure
from app.db import execute_sql, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.monitor import create_scan_job, record_scan_candidate, scan_site


class CatalogDiscoveryTests(unittest.TestCase):
    def test_product_discovery_excludes_non_product_sitemap_urls(self) -> None:
        candidates = discover_product_candidates(
            "https://store.example.com/",
            sitemap_documents={
                "https://store.example.com/sitemap.xml": """
                    <urlset>
                      <url><loc>https://store.example.com/products/pump</loc></url>
                      <url><loc>https://store.example.com/blogs/news</loc></url>
                      <url><loc>https://store.example.com/collections/pumps</loc></url>
                    </urlset>
                """,
            },
        )

        self.assertEqual([candidate.url for candidate in candidates], ["https://store.example.com/products/pump"])

    def test_fetch_result_records_retry_after_for_rate_limit(self) -> None:
        result = fetch_result_from_response(
            "https://store.example.com/products/pump",
            status_code=429,
            headers={"Retry-After": "17"},
            content="Too many requests",
        )

        self.assertEqual(result.error_category, "rate_limited")
        self.assertEqual(result.retry_after_seconds, 17)
        self.assertIsNone(result.content)

    def test_rate_limited_fetch_result_raises_structured_product_error(self) -> None:
        result = fetch_result_from_response(
            "https://store.example.com/products/pump",
            status_code=429,
            headers={"Retry-After": "17"},
            content="Too many requests",
        )

        with self.assertRaises(ProductFetchError) as raised:
            raise_for_fetch_failure(result)

        self.assertEqual(raised.exception.error_category, "rate_limited")
        self.assertEqual(raised.exception.http_status, 429)


class CatalogCandidatePersistenceTests(unittest.TestCase):
    def test_keeps_stored_candidate_when_a_later_attempt_is_rate_limited(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"candidate-{marker}@monitor.internal"
        candidate_url = f"https://store-{marker}.example.com/products/pump"
        with get_db() as db:
            user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
            site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": user_id,
                    "name": "Candidate store",
                    "url": f"https://store-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": json_dumps(["product_new"]),
                },
            )
            source_id = insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": site_id,
                    "source_type": "homepage",
                    "url": f"https://store-{marker}.example.com",
                    "scan_interval_minutes": 60,
                },
            )
            job_id = insert_row(
                db,
                "scan_jobs",
                {"site_id": site_id, "source_id": source_id, "job_type": "source_scan", "trigger_type": "baseline"},
            )
        try:
            record_scan_candidate(job_id, candidate_url, status="stored", http_status=200)
            record_scan_candidate(job_id, candidate_url, status="rate_limited", http_status=429, error_category="rate_limited")

            with get_db() as db:
                row = row_to_dict(fetchone(db, "SELECT * FROM scan_job_candidates WHERE job_id = ?", (job_id,)))
            self.assertEqual(row["status"], "stored")
            self.assertEqual(row["attempt_count"], 2)
            self.assertEqual(row["http_status"], 200)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


class CatalogBaselineQualityTests(unittest.TestCase):
    def test_rate_limited_candidates_leave_baseline_incomplete(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"quality-{marker}@monitor.internal"
        site_url = f"https://quality-{marker}.example.com"
        with get_db() as db:
            user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
            site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": user_id,
                    "name": "Quality store",
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
        candidates = [ProductCandidate(f"{site_url}/products/{name}") for name in ("stored", "limited-one", "limited-two")]
        stored_product = ExtractedProduct(
            url=candidates[0].url,
            title="Stored product",
            description="A product that was read successfully",
            image_url=None,
            price="$19",
            price_amount=19.0,
            currency="USD",
            compare_at_price=None,
            availability="in_stock",
            variant_count=1,
            variants=[],
            features=["Compact"],
            extraction_source="test",
            confidence_score=0.95,
            field_confidence={"price": 1.0},
            confidence_reasons=[],
            content_hash=f"quality-{marker}",
            raw_text="Stored product",
        )
        try:
            with (
                patch("app.monitor.discover_candidates", new=AsyncMock(return_value=candidates)),
                patch("app.monitor.capture_source_snapshot", new=AsyncMock(return_value=None)),
                patch(
                    "app.monitor.extract_candidate_product",
                    new=AsyncMock(
                        side_effect=[
                            stored_product,
                            ProductFetchError("rate_limited", 429, retry_after_seconds=30),
                            ProductFetchError("rate_limited", 429, retry_after_seconds=30),
                        ]
                    ),
                ),
            ):
                result = asyncio.run(scan_site(site_id, trigger_type="baseline", job_id=job_id))

            self.assertEqual(result["progress"]["quality"]["stored_product_count"], 1)
            self.assertEqual(result["progress"]["quality"]["rate_limited_count"], 2)
            self.assertEqual(result["progress"]["quality"]["baseline_state"], "incomplete")
            self.assertFalse(result["progress"]["baseline_completed"])
            with get_db() as db:
                job = row_to_dict(fetchone(db, "SELECT * FROM scan_jobs WHERE id = ?", (job_id,)))
            self.assertEqual(job["status"], "partial_success")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
