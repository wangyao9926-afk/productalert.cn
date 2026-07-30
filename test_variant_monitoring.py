from __future__ import annotations

import unittest
from uuid import uuid4

from app.crawler import ProductCandidate, product_from_shopify_payload
from app.db import execute_sql, fetchall, get_db, init_db, insert_row, row_to_dict
from app.monitor import extract_and_store_product
from app.main import app
from fastapi.testclient import TestClient


class VariantMonitoringTests(unittest.TestCase):
    def test_shopify_product_exposes_stable_variant_price_and_stock_records(self) -> None:
        product = product_from_shopify_payload(
            ProductCandidate(
                url="https://variants.example.com/products/trail-pack",
                payload={
                    "kind": "shopify_product",
                    "product": {
                        "title": "Trail Pack",
                        "options": [{"name": "Color"}, {"name": "Size"}],
                        "variants": [
                            {
                                "id": 101,
                                "sku": "TP-RED-S",
                                "title": "Red / Small",
                                "option1": "Red",
                                "option2": "Small",
                                "price": "39.00",
                                "compare_at_price": "49.00",
                                "available": True,
                            },
                            {
                                "id": 102,
                                "sku": "TP-BLU-L",
                                "title": "Blue / Large",
                                "option1": "Blue",
                                "option2": "Large",
                                "price": "45.00",
                                "compare_at_price": None,
                                "available": False,
                            },
                        ],
                    },
                },
            )
        )

        assert product is not None
        self.assertEqual(product.variant_count, 2)
        self.assertEqual(product.variants[0].external_id, "101")
        self.assertEqual(product.variants[0].sku, "TP-RED-S")
        self.assertEqual(product.variants[0].option_values, ["Color: Red", "Size: Small"])
        self.assertEqual(product.variants[0].price_amount, 39.0)
        self.assertEqual(product.variants[0].compare_at_price, 49.0)
        self.assertEqual(product.variants[0].availability, "in_stock")
        self.assertEqual(product.variants[1].availability, "out_of_stock")


class VariantPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_shopify_variants_are_saved_by_stable_external_id(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        with get_db() as db:
            site_id = insert_row(
                db,
                "sites",
                {
                    "user_id": 1,
                    "name": "Variant persistence site",
                    "url": f"https://variant-store-{marker}.example.com",
                    "scan_interval_minutes": 60,
                    "notification_events": "[\"product_new\"]",
                },
            )
            source_id = insert_row(
                db,
                "monitor_sources",
                {
                    "site_id": site_id,
                    "source_type": "listing_page",
                    "url": f"https://variant-store-{marker}.example.com/collections/new",
                    "scan_interval_minutes": 60,
                },
            )
        candidate = ProductCandidate(
            url=f"https://variant-store-{marker}.example.com/products/trail-pack",
            payload={
                "kind": "shopify_product",
                "product": {
                    "title": "Trail Pack",
                    "options": [{"name": "Color"}],
                    "variants": [
                        {"id": 101, "sku": "TP-RED", "title": "Red", "option1": "Red", "price": "39.00", "available": True},
                        {"id": 102, "sku": "TP-BLU", "title": "Blue", "option1": "Blue", "price": "45.00", "available": False},
                    ],
                },
            },
        )
        try:
            await extract_and_store_product(
                candidate,
                {"id": source_id, "site_id": site_id, "site_name": "Variant persistence site", "url": candidate.url},
                source_id,
                discovery_status="baseline",
                notify=False,
                record_changes=False,
            )
            with get_db() as db:
                product = row_to_dict(fetchall(db, "SELECT * FROM products WHERE site_id = ?", (site_id,))[0])
                variants = [row_to_dict(row) for row in fetchall(db, "SELECT * FROM product_variants WHERE product_id = ? ORDER BY external_id", (product["id"],))]
            self.assertEqual([(item["external_id"], item["sku"], item["price_amount"], item["availability"]) for item in variants], [
                ("101", "TP-RED", 39.0, "in_stock"),
                ("102", "TP-BLU", 45.0, "out_of_stock"),
            ])
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))

    async def test_variant_price_and_stock_changes_create_events_when_product_totals_do_not_change(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        url = f"https://variant-events-{marker}.example.com/products/trail-pack"
        with get_db() as db:
            site_id = insert_row(db, "sites", {"user_id": 1, "name": "Variant event site", "url": f"https://variant-events-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"product_new\"]"})
            source_id = insert_row(db, "monitor_sources", {"site_id": site_id, "source_type": "listing_page", "url": f"https://variant-events-{marker}.example.com/collections/new", "scan_interval_minutes": 60})
            insert_row(db, "source_snapshots", {"source_id": source_id, "url": url, "content_hash": "baseline-content", "text_hash": "baseline-text"})
        source_data = {"id": source_id, "site_id": site_id, "site_name": "Variant event site", "url": url}
        baseline = ProductCandidate(
            url=url,
            payload={"kind": "shopify_product", "product": {"title": "Trail Pack", "variants": [
                {"id": 101, "sku": "TP-RED", "title": "Red", "price": "39.00", "available": True},
                {"id": 102, "sku": "TP-BLU", "title": "Blue", "price": "45.00", "available": False},
                {"id": 103, "sku": "TP-GRN", "title": "Green", "price": "60.00", "available": False},
            ]}},
        )
        changed = ProductCandidate(
            url=url,
            payload={"kind": "shopify_product", "product": {"title": "Trail Pack", "variants": [
                {"id": 101, "sku": "TP-RED", "title": "Red", "price": "39.00", "available": True},
                {"id": 102, "sku": "TP-BLU", "title": "Blue", "price": "46.00", "available": True},
                {"id": 103, "sku": "TP-GRN", "title": "Green", "price": "60.00", "available": False},
            ]}},
        )
        try:
            await extract_and_store_product(baseline, source_data, source_id, discovery_status="baseline", notify=False, record_changes=False)
            await extract_and_store_product(changed, source_data, source_id, discovery_status="known", notify=False, record_changes=True)
            with get_db() as db:
                events = [row_to_dict(row) for row in fetchall(db, "SELECT * FROM change_events WHERE site_id = ? ORDER BY id", (site_id,))]
            self.assertEqual([event["change_type"] for event in events], ["price_change", "availability_change"])
            self.assertEqual([event["diff"][0]["variant_external_id"] for event in events], ["102", "102"])
            self.assertEqual(events[0]["diff"][0]["field"], "variant_price")
            self.assertEqual(events[1]["diff"][0]["field"], "variant_availability")
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


class VariantApiTests(unittest.TestCase):
    def test_only_the_product_owner_can_list_variant_records(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"variant-owner-{marker}@monitor.internal"
        stranger_email = f"variant-stranger-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            stranger = client.post("/api/auth/register", json={"email": stranger_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(stranger.status_code, 200, stranger.text)
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {"user_id": owner.json()["user"]["id"], "name": "Variant API site", "url": f"https://variant-api-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"product_new\"]"},
                )
                product_id = insert_row(
                    db,
                    "products",
                    {"site_id": site_id, "url": f"https://variant-api-{marker}.example.com/products/trail-pack", "title": "Trail Pack", "content_hash": marker},
                )
                insert_row(
                    db,
                    "product_variants",
                    {"product_id": product_id, "external_id": "101", "sku": "TP-RED", "title": "Red", "option_values": "Color: Red", "price_amount": 39.0, "availability": "in_stock"},
                )
            owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
            stranger_headers = {"Authorization": f"Bearer {stranger.json()['token']}"}

            owner_response = client.get(f"/api/products/{product_id}/variants", headers=owner_headers)
            stranger_response = client.get(f"/api/products/{product_id}/variants", headers=stranger_headers)

            self.assertEqual(owner_response.status_code, 200, owner_response.text)
            self.assertEqual(owner_response.json()[0]["sku"], "TP-RED")
            self.assertEqual(stranger_response.status_code, 404, stranger_response.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, stranger_email))


if __name__ == "__main__":
    unittest.main()
