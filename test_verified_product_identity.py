from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.crawler import ProductCandidate, product_from_shopify_payload
from app.db import execute_sql, fetchall, get_db, init_db, insert_row, json_dumps
from app.main import app
from app.monitor import refresh_product_match_groups, sync_product_identifiers


class VerifiedProductIdentityTests(unittest.TestCase):
    def test_shopify_identifiers_are_normalized_and_persisted(self) -> None:
        product = product_from_shopify_payload(
            ProductCandidate(
                url="https://identity.example.com/products/trail-pack",
                payload={
                    "kind": "shopify_product",
                    "product": {
                        "id": 501,
                        "title": "Trail Pack",
                        "variants": [
                            {"id": 101, "sku": " trail-42 ", "barcode": "12-34567890123", "price": "39.00", "available": True},
                        ],
                    },
                },
            )
        )

        assert product is not None
        self.assertIn(("sku", "TRAIL-42"), {(item.kind, item.value) for item in product.identifiers})
        self.assertIn(("gtin", "1234567890123"), {(item.kind, item.value) for item in product.identifiers})
        self.assertIn(("platform_product_id", "501"), {(item.kind, item.value) for item in product.identifiers})

        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(db, "sites", {"user_id": 1, "name": "Identity site", "url": f"https://identity-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": "[\"product_new\"]"})
                product_id = insert_row(db, "products", {"site_id": site_id, "url": f"https://identity-{marker}.example.com/products/trail-pack", "title": "Trail Pack", "content_hash": marker})
                sync_product_identifiers(db, product_id, product)
                identifiers = {(row["identifier_type"], row["normalized_value"]) for row in fetchall(db, "SELECT * FROM product_identifiers WHERE product_id = ?", (product_id,))}
            self.assertIn(("sku", "TRAIL-42"), identifiers)
            self.assertIn(("gtin", "1234567890123"), identifiers)
            self.assertIn(("platform_product_id", "501"), identifiers)
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))

    def test_exact_sku_creates_cross_site_group_visible_only_to_owner(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"identity-owner-{marker}@monitor.internal"
        stranger_email = f"identity-stranger-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            stranger = client.post("/api/auth/register", json={"email": stranger_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(stranger.status_code, 200, stranger.text)
            owner_id = owner.json()["user"]["id"]
            with get_db() as db:
                first_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store A", "url": f"https://a-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                second_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store B", "url": f"https://b-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                first_product = insert_row(db, "products", {"site_id": first_site, "url": f"https://a-{marker}.example.com/products/trail", "title": "Trail Pack A", "price_amount": 39, "availability": "in_stock", "content_hash": f"a-{marker}"})
                second_product = insert_row(db, "products", {"site_id": second_site, "url": f"https://b-{marker}.example.com/products/trail", "title": "Trail Pack B", "price_amount": 45, "availability": "out_of_stock", "content_hash": f"b-{marker}"})
                for product_id in (first_product, second_product):
                    insert_row(db, "product_identifiers", {"product_id": product_id, "identifier_type": "sku", "normalized_value": "TRAIL-42", "raw_value": "trail-42", "provenance": "shopify_variant"})
                refresh_product_match_groups(db, first_product)
                refresh_product_match_groups(db, second_product)

            owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
            stranger_headers = {"Authorization": f"Bearer {stranger.json()['token']}"}
            response = client.get(f"/api/products/{first_product}/matches", headers=owner_headers)
            forbidden = client.get(f"/api/products/{first_product}/matches", headers=stranger_headers)

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()[0]["identifier_value"], "TRAIL-42")
            self.assertEqual(len(response.json()[0]["products"]), 2)
            self.assertEqual(forbidden.status_code, 404, forbidden.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, stranger_email))


if __name__ == "__main__":
    unittest.main()
