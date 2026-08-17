from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app


class BaselineProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        init_db()
        marker = uuid4().hex
        self.owner_email = f"baseline-products-owner-{marker}@monitor.internal"
        self.other_email = f"baseline-products-other-{marker}@monitor.internal"
        self.client = TestClient(app)
        self.other_client = TestClient(app)
        owner = self.client.post("/api/auth/register", json={"email": self.owner_email, "password": "test-password-123"})
        other = self.other_client.post("/api/auth/register", json={"email": self.other_email, "password": "test-password-123"})
        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertEqual(other.status_code, 200, other.text)
        self.owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
        self.other_headers = {"Authorization": f"Bearer {other.json()['token']}"}
        self.product_url = f"https://baseline-products-{marker}.example.com/products/waterproof-bag"
        with get_db() as db:
            self.site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": owner.json()["user"]["id"],
                    "name": "Baseline products site",
                    "url": f"https://baseline-products-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": json_dumps(["product_new"]),
                },
            )
            source_id = insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": self.site_id,
                    "source_type": "homepage",
                    "url": f"https://baseline-products-{marker}.example.com",
                    "scan_interval_minutes": 60,
                },
            )
            self.product_id = insert_row(
                db,
                "products",
                {
                    "site_id": self.site_id,
                    "source_id": source_id,
                    "url": self.product_url,
                    "title": "Waterproof Bag",
                    "description": "A waterproof everyday bag",
                    "image_url": "https://cdn.example.com/bag.jpg",
                    "price": "$29.00",
                    "price_amount": 29.0,
                    "currency": "USD",
                    "compare_at_price": 39.0,
                    "availability": "in_stock",
                    "variant_count": 2,
                    "item_type": "product_detail",
                    "review_status": "unreviewed",
                    "discovery_status": "baseline",
                    "extraction_source": "json_ld",
                    "confidence_score": 0.95,
                    "field_confidence": json_dumps({"price": 1.0}),
                    "confidence_reasons": json_dumps([]),
                    "features": json_dumps(["Water resistant"]),
                    "content_hash": "baseline-product-hash",
                    "raw_text": "Waterproof Bag",
                },
            )
            self.false_positive_url = f"https://baseline-products-{marker}.example.com/collections/products/waterproof-bag"
            self.false_positive_id = insert_row(
                db,
                "products",
                {
                    "site_id": self.site_id,
                    "source_id": source_id,
                    "url": self.false_positive_url,
                    "title": "Collection landing page",
                    "item_type": "collection_page",
                    "review_status": "false_positive",
                    "content_hash": "false-positive-collection-hash",
                    "raw_text": "Collection landing page",
                },
            )
            self.job_id = insert_row(
                db,
                "scan_jobs",
                {
                    "site_id": self.site_id,
                    "job_type": "site_scan",
                    "trigger_type": "baseline",
                    "status": "success",
                    "result": json_dumps({"progress": {"baseline_completed": True, "product_count": 1}}),
                },
            )
            self.source_job_id = insert_row(
                db,
                "scan_jobs",
                {
                    "parent_job_id": self.job_id,
                    "site_id": self.site_id,
                    "source_id": source_id,
                    "job_type": "source_scan",
                    "trigger_type": "baseline",
                    "status": "partial_success",
                },
            )
            insert_row(
                db,
                "scan_job_candidates",
                {
                    "job_id": self.source_job_id,
                    "site_id": self.site_id,
                    "source_id": source_id,
                    "url": self.product_url,
                    "canonical_key": "baseline-products/waterproof-bag",
                    "status": "stored",
                    "http_status": 200,
                },
            )
            self.failed_candidate_url = f"https://baseline-products-{marker}.example.com/products/not-parsed"
            insert_row(
                db,
                "scan_job_candidates",
                {
                    "job_id": self.source_job_id,
                    "site_id": self.site_id,
                    "source_id": source_id,
                    "url": self.failed_candidate_url,
                    "canonical_key": "baseline-products/not-parsed",
                    "status": "parse_failed",
                    "http_status": 200,
                    "error_category": "parse_failed",
                },
            )

    def tearDown(self) -> None:
        with get_db() as db:
            execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (self.owner_email, self.other_email))

    def test_owner_reads_site_baseline_summary_and_product_fields(self) -> None:
        summary = self.client.get(f"/api/sites/{self.site_id}/baseline-summary", headers=self.owner_headers)

        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["product_count"], 1)
        self.assertTrue(summary.json()["baseline_completed"])
        self.assertEqual(summary.json()["latest_job"]["id"], self.job_id)

        products = self.client.get(f"/api/products?site_id={self.site_id}", headers=self.owner_headers)

        self.assertEqual(products.status_code, 200, products.text)
        self.assertEqual(len(products.json()), 1)
        product = products.json()[0]
        self.assertEqual(product["item_type"], "product_detail")
        self.assertEqual(product["features"], ["Water resistant"])
        self.assertEqual(product["description"], "A waterproof everyday bag")
        self.assertEqual(product["image_url"], "https://cdn.example.com/bag.jpg")
        self.assertEqual(product["compare_at_price"], 39.0)
        self.assertEqual(product["variant_count"], 2)
        self.assertEqual(product["url"], self.product_url)
        self.assertEqual(product["availability"], "in_stock")
        self.assertEqual(product["currency"], "USD")

        detail = self.client.get(f"/api/products/{self.product_id}", headers=self.owner_headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["id"], self.product_id)

        hidden_detail = self.client.get(f"/api/products/{self.false_positive_id}", headers=self.owner_headers)
        self.assertEqual(hidden_detail.status_code, 404, hidden_detail.text)

        sites = self.client.get("/api/sites", headers=self.owner_headers)
        self.assertEqual(sites.status_code, 200, sites.text)
        site = next(item for item in sites.json() if item["id"] == self.site_id)
        self.assertEqual(site["product_count"], 1)

    def test_site_scoped_product_list_is_not_truncated_by_global_preview_limit(self) -> None:
        with get_db() as db:
            for index in range(205):
                insert_row(
                    db,
                    "products",
                    {
                        "site_id": self.site_id,
                        "url": f"https://baseline-products-extra.example.com/products/{index}",
                        "title": f"Extra product {index}",
                        "item_type": "product_detail",
                        "review_status": "confirmed",
                        "content_hash": f"extra-product-hash-{index}",
                        "raw_text": f"Extra product {index}",
                    },
                )

        products = self.client.get(f"/api/products?site_id={self.site_id}", headers=self.owner_headers)

        self.assertEqual(products.status_code, 200, products.text)
        self.assertEqual(len(products.json()), 206)

    def test_other_user_cannot_read_site_baseline_summary(self) -> None:
        response = self.other_client.get(f"/api/sites/{self.site_id}/baseline-summary", headers=self.other_headers)

        self.assertEqual(response.status_code, 404, response.text)

    def test_owner_can_read_issue_candidates_from_site_baseline(self) -> None:
        response = self.client.get(f"/api/scan-jobs/{self.job_id}/candidates", headers=self.owner_headers)

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["job_id"], self.job_id)
        self.assertEqual(payload["stored_count"], 1)
        self.assertEqual(payload["issue_count"], 1)
        self.assertEqual(payload["items"][0]["url"], self.failed_candidate_url)
        self.assertEqual(payload["items"][0]["status"], "parse_failed")

        forbidden = self.other_client.get(f"/api/scan-jobs/{self.job_id}/candidates", headers=self.other_headers)
        self.assertEqual(forbidden.status_code, 404, forbidden.text)


if __name__ == "__main__":
    unittest.main()
