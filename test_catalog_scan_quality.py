from __future__ import annotations

import asyncio
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.crawler import CatalogDiscoveryResult, ExtractedProduct, ProductCandidate, ProductFetchError, classify_product_url, discover_product_candidates, fetch_result_from_response, jsonld_item_list_candidates, matches_catalog_candidate_rules, merge_catalog_candidates, product_from_woocommerce_payload, raise_for_fetch_failure, shopify_product_candidates, woocommerce_product_candidates_from_payload
from app.db import execute_sql, fetchall, fetchone, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.db_sqlite_maintenance import migrate_product_classification
from app.monitor import create_scan_job, record_scan_candidate, scan_site
from app.rate_limit import domain_cooldown_remaining, record_domain_rate_limit, record_domain_success, reset_domain_rate_limits


class CatalogDiscoveryTests(unittest.TestCase):
    def test_product_url_classifier_rejects_collection_and_compare_pages(self) -> None:
        self.assertEqual(classify_product_url("https://shop.example.com/collections/products/tent"), ("collection_page", "false_positive"))
        self.assertEqual(classify_product_url("https://shop.example.com/product/compare"), ("utility_page", "false_positive"))
        self.assertEqual(classify_product_url("https://shop.example.com/products/tent"), ("product_detail", "confirmed"))

    def test_product_classification_maintenance_reclassifies_existing_false_positive(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"classification-{marker}@monitor.internal"
        try:
            with get_db() as db:
                user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
                site_id = insert_row(db, "sites", {"user_id": user_id, "name": "Classifier store", "url": f"https://shop-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                product_id = insert_row(db, "products", {"site_id": site_id, "url": f"https://shop-{marker}.example.com/collections/products/tent", "title": "Collection", "item_type": "product_detail", "review_status": "confirmed", "content_hash": "classification-test-hash", "raw_text": "Collection"})
                migrate_product_classification(db)
                product = row_to_dict(fetchone(db, "SELECT item_type, review_status FROM products WHERE id = ?", (product_id,)))
            self.assertEqual(product["item_type"], "collection_page")
            self.assertEqual(product["review_status"], "false_positive")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))

    def test_merges_catalog_candidates_and_preserves_all_discovery_sources(self) -> None:
        candidates = merge_catalog_candidates(
            [
                ProductCandidate(
                    "https://store.example.com/product/air-pump/",
                    "Air pump",
                    {"kind": "woocommerce_product"},
                    ("woocommerce_store_api",),
                ),
                ProductCandidate(
                    "https://store.example.com/product/air-pump?utm_source=sitemap",
                    "",
                    None,
                    ("product_sitemap", "json_ld_item_list"),
                ),
            ],
            limit=10,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].payload, {"kind": "woocommerce_product"})
        self.assertEqual(
            candidates[0].discovery_sources,
            ("woocommerce_store_api", "product_sitemap", "json_ld_item_list"),
        )

    def test_woocommerce_payload_creates_product_candidates_with_public_catalog_evidence(self) -> None:
        candidates = woocommerce_product_candidates_from_payload(
            [
                {
                    "id": 34,
                    "name": "WordPress Pennant",
                    "permalink": "https://store.example.com/shop/wordpress-pennant/",
                }
            ],
            "https://store.example.com/",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://store.example.com/shop/wordpress-pennant/")
        self.assertEqual(candidates[0].payload["kind"], "woocommerce_product")
        self.assertEqual(candidates[0].discovery_sources, ("woocommerce_store_api",))

    def test_jsonld_item_list_creates_product_candidate_when_url_has_no_product_path(self) -> None:
        candidates = jsonld_item_list_candidates(
            """
            <script type="application/ld+json">
              {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
                {"@type":"ListItem","position":1,"item":{"@type":"Product","name":"Quiet Pump","url":"/shop/quiet-pump"}}
              ]}
            </script>
            """,
            "https://store.example.com/collections/new",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].url, "https://store.example.com/shop/quiet-pump")
        self.assertEqual(candidates[0].payload["kind"], "jsonld_product")
        self.assertEqual(candidates[0].discovery_sources, ("json_ld_item_list",))

    def test_confirmed_platform_product_bypasses_generic_url_relevance_rule_but_honors_exclusions(self) -> None:
        candidate = ProductCandidate(
            "https://store.example.com/shop/quiet-pump",
            "Quiet Pump",
            {"kind": "woocommerce_product"},
            ("woocommerce_store_api",),
        )

        self.assertTrue(matches_catalog_candidate_rules(candidate, [], [], require_relevance=True))
        self.assertFalse(matches_catalog_candidate_rules(candidate, [], ["quiet"], require_relevance=True))

    def test_woocommerce_payload_extracts_price_availability_image_and_sku_without_a_second_page_request(self) -> None:
        product = product_from_woocommerce_payload(
            ProductCandidate(
                "https://store.example.com/shop/quiet-pump/",
                "Quiet Pump",
                {
                    "kind": "woocommerce_product",
                    "product": {
                        "id": 34,
                        "name": "Quiet Pump",
                        "sku": "PUMP-34",
                        "description": "<p>A quiet and compact air pump.</p>",
                        "images": [{"src": "https://cdn.example.com/pump.jpg"}],
                        "is_in_stock": True,
                        "prices": {"price": "2599", "regular_price": "2999", "currency_code": "USD", "currency_minor_unit": 2},
                    },
                },
                ("woocommerce_store_api",),
            )
        )

        self.assertIsNotNone(product)
        assert product is not None
        self.assertEqual(product.price, "$25.99")
        self.assertEqual(product.compare_at_price, 29.99)
        self.assertEqual(product.availability, "in_stock")
        self.assertEqual(product.image_url, "https://cdn.example.com/pump.jpg")
        self.assertEqual(product.identifiers[0].value, "34")

    def test_rate_limit_cooldown_honors_retry_after_then_uses_bounded_backoff(self) -> None:
        reset_domain_rate_limits()
        with patch("app.rate_limit.time.monotonic", return_value=100.0):
            self.assertEqual(record_domain_rate_limit("https://store.example.com/products/pump", retry_after_seconds=60), 60)
            self.assertEqual(domain_cooldown_remaining("https://store.example.com/products/other"), 60.0)

        with patch("app.rate_limit.time.monotonic", return_value=200.0):
            self.assertEqual(record_domain_rate_limit("https://retry.example.com/products/pump"), 30)
        with patch("app.rate_limit.time.monotonic", return_value=201.0):
            self.assertEqual(record_domain_rate_limit("https://retry.example.com/products/other"), 60)
            self.assertEqual(domain_cooldown_remaining("https://retry.example.com/"), 60.0)

        record_domain_success("https://retry.example.com/products/other")
        with patch("app.rate_limit.time.monotonic", return_value=300.0):
            self.assertEqual(record_domain_rate_limit("https://retry.example.com/products/final"), 30)

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

    def test_shopify_catalog_rate_limit_registers_domain_cooldown(self) -> None:
        response = type("Response", (), {"status_code": 429, "headers": {"Retry-After": "60"}})()
        client = type("Client", (), {"get": AsyncMock(return_value=response)})()

        with (
            patch("app.crawler.validate_public_http_url", side_effect=lambda url: url),
            patch("app.crawler.record_domain_rate_limit") as record_cooldown,
        ):
            candidates = asyncio.run(shopify_product_candidates(client, "https://store.example.com/"))

        self.assertEqual(candidates, [])
        record_cooldown.assert_called_once_with("https://store.example.com/products.json", 60)


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
    def test_unparseable_product_candidate_is_not_counted_as_verified_catalog_product(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"unparseable-{marker}@monitor.internal"
        site_url = f"https://unparseable-{marker}.example.com"
        with get_db() as db:
            user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
            site_id = insert_row(
                db,
                "sites",
                {"user_id": user_id, "name": "Unparseable catalog", "url": site_url, "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])},
            )
            insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "homepage", "url": site_url, "scan_interval_minutes": 60})
        job_id = create_scan_job(site_id, None, "site_scan", "baseline")
        candidates = [
            ProductCandidate(
                f"{site_url}/shop/verified",
                payload={"kind": "woocommerce_product", "product": {"id": 1}},
                discovery_sources=("woocommerce_store_api",),
            ),
            ProductCandidate(f"{site_url}/products/not-a-product"),
        ]
        verified_product = ExtractedProduct(
            url=candidates[0].url,
            title="Verified product",
            description="A verified product page",
            image_url=None,
            price="$19",
            price_amount=19.0,
            currency="USD",
            compare_at_price=None,
            availability="in_stock",
            variant_count=1,
            variants=[],
            features=["Verified"],
            extraction_source="test",
            confidence_score=0.95,
            field_confidence={"price": 1.0},
            confidence_reasons=[],
            content_hash=f"unparseable-{marker}",
            raw_text="Verified product",
        )
        discovery = CatalogDiscoveryResult(candidates=candidates, reference_count=2, discovery_source_counts={"product_sitemap": 2}, adapter_attempts=[])
        try:
            with (
                patch("app.monitor.discover_catalog", new=AsyncMock(return_value=discovery)),
                patch("app.monitor.capture_source_snapshot", new=AsyncMock(return_value=None)),
                patch("app.monitor.extract_candidate_product", new=AsyncMock(side_effect=[verified_product, None])),
            ):
                result = asyncio.run(scan_site(site_id, trigger_type="baseline", job_id=job_id))

            quality = result["progress"]["quality"]
            self.assertEqual(quality["stored_product_count"], 1)
            self.assertEqual(quality["parse_failed_count"], 1)
            self.assertEqual(result["progress"]["product_count"], 1)
            with get_db() as db:
                source_job = fetchone(db, "SELECT id FROM scan_jobs WHERE parent_job_id = ? ORDER BY id DESC LIMIT 1", (job_id,))
                candidate_statuses = [row["status"] for row in fetchall(db, "SELECT status FROM scan_job_candidates WHERE job_id = ? ORDER BY id", (source_job["id"],))]
            self.assertEqual(candidate_statuses, ["stored", "parse_failed"])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))

    def test_scan_quality_exposes_catalog_reference_sources_and_incomplete_coverage(self) -> None:
        init_db()
        marker = uuid4().hex
        email = f"coverage-{marker}@monitor.internal"
        site_url = f"https://coverage-{marker}.example.com"
        with get_db() as db:
            user_id = insert_row(db, "users", {"email": email, "password_hash": "not-used"})
            site_id = insert_row(
                db,
                "sites",
                {"user_id": user_id, "name": "Coverage store", "url": site_url, "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])},
            )
            insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "homepage", "url": site_url, "scan_interval_minutes": 60})
        job_id = create_scan_job(site_id, None, "site_scan", "baseline")
        candidates = [ProductCandidate(f"{site_url}/shop/quiet-pump", "Quiet Pump", {"kind": "woocommerce_product"}, ("woocommerce_store_api",))]
        stored_product = ExtractedProduct(
            url=candidates[0].url, title="Quiet Pump", description="Quiet pump", image_url=None,
            price="$19", price_amount=19.0, currency="USD", compare_at_price=None,
            availability="in_stock", variant_count=1, variants=[], features=["Quiet"],
            extraction_source="test", confidence_score=0.95, field_confidence={"price": 1.0},
            confidence_reasons=[], content_hash=f"coverage-{marker}", raw_text="Quiet pump",
        )
        discovery = CatalogDiscoveryResult(
            candidates=candidates,
            reference_count=2,
            discovery_source_counts={"woocommerce_store_api": 1},
            adapter_attempts=[{"adapter": "woocommerce_store_api", "status": "available", "http_status": 200}],
        )
        try:
            with (
                patch("app.monitor.discover_catalog", new=AsyncMock(return_value=discovery)),
                patch("app.monitor.capture_source_snapshot", new=AsyncMock(return_value=None)),
                patch("app.monitor.extract_candidate_product", new=AsyncMock(return_value=stored_product)),
            ):
                result = asyncio.run(scan_site(site_id, trigger_type="baseline", job_id=job_id))

            quality = result["progress"]["quality"]
            self.assertEqual(quality["catalog_reference_count"], 2)
            self.assertEqual(quality["discovery_source_counts"], {"woocommerce_store_api": 1})
            self.assertEqual(quality["coverage_state"], "best_effort")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))

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
        discovery = CatalogDiscoveryResult(
            candidates=candidates,
            reference_count=None,
            discovery_source_counts={"product_sitemap": len(candidates)},
            adapter_attempts=[{"adapter": "shopify_api", "status": "limited", "http_status": 429}],
        )
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
                patch("app.monitor.discover_catalog", new=AsyncMock(return_value=discovery)),
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
            self.assertEqual(result["progress"]["quality"]["rate_limited_count"], 1)
            self.assertEqual(result["progress"]["quality"]["pending_retry_count"], 1)
            self.assertEqual(result["progress"]["quality"]["baseline_state"], "incomplete")
            self.assertFalse(result["progress"]["baseline_completed"])
            self.assertEqual(result["status"], "partial_success")
            with get_db() as db:
                job = row_to_dict(fetchone(db, "SELECT * FROM scan_jobs WHERE id = ?", (job_id,)))
            self.assertEqual(job["status"], "partial_success")
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (email,))


if __name__ == "__main__":
    unittest.main()
