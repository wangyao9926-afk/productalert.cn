from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, json_dumps
from app.main import app
from app.monitor import refresh_product_match_groups


class PriceMatrixTests(unittest.TestCase):
    def test_owner_can_list_verified_product_matches_with_numeric_prices(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"matrix-product-owner-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            owner_id = owner.json()["user"]["id"]
            with get_db() as db:
                first_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store A", "url": f"https://a-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                second_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store B", "url": f"https://b-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                first_product = insert_row(db, "products", {"site_id": first_site, "url": f"https://a-{marker}.example.com/products/trail", "title": "Trail Pack A", "price": "39.00", "price_amount": 39, "currency": "USD", "availability": "in_stock", "content_hash": f"a-{marker}"})
                second_product = insert_row(db, "products", {"site_id": second_site, "url": f"https://b-{marker}.example.com/products/trail", "title": "Trail Pack B", "price": "45.00", "price_amount": 45, "currency": "USD", "availability": "out_of_stock", "content_hash": f"b-{marker}"})
                for product_id in (first_product, second_product):
                    insert_row(db, "product_identifiers", {"product_id": product_id, "identifier_type": "sku", "normalized_value": "TRAIL-42", "raw_value": "trail-42", "provenance": "shopify_variant"})
                refresh_product_match_groups(db, first_product)
                refresh_product_match_groups(db, second_product)

            response = client.get(f"/api/products/{first_product}/matches", headers={"Authorization": f"Bearer {owner.json()['token']}"})

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([item["price_amount"] for item in response.json()[0]["products"]], [39, 45])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (owner_email,))

    def test_owner_can_list_verified_cross_site_price_groups(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"matrix-owner-{marker}@monitor.internal"
        client = TestClient(app)
        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            owner_id = owner.json()["user"]["id"]
            with get_db() as db:
                first_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store A", "url": f"https://a-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                second_site = insert_row(db, "sites", {"user_id": owner_id, "name": "Store B", "url": f"https://b-{marker}.example.com", "scan_interval_minutes": 60, "notification_events": json_dumps(["product_new"])})
                first_product = insert_row(db, "products", {"site_id": first_site, "url": f"https://a-{marker}.example.com/products/trail", "title": "Trail Pack A", "price": "39.00", "price_amount": 39, "currency": "USD", "availability": "in_stock", "content_hash": f"a-{marker}"})
                second_product = insert_row(db, "products", {"site_id": second_site, "url": f"https://b-{marker}.example.com/products/trail", "title": "Trail Pack B", "price": "45.00", "price_amount": 45, "currency": "USD", "availability": "out_of_stock", "content_hash": f"b-{marker}"})
                for product_id in (first_product, second_product):
                    insert_row(db, "product_identifiers", {"product_id": product_id, "identifier_type": "sku", "normalized_value": "TRAIL-42", "raw_value": "trail-42", "provenance": "shopify_variant"})
                refresh_product_match_groups(db, first_product)
                refresh_product_match_groups(db, second_product)

            response = client.get("/api/product-match-groups", headers={"Authorization": f"Bearer {owner.json()['token']}"})

            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(len(response.json()), 1)
            self.assertEqual(response.json()[0]["identifier_value"], "TRAIL-42")
            self.assertEqual([item["site_name"] for item in response.json()[0]["products"]], ["Store A", "Store B"])
            self.assertEqual([item["price_amount"] for item in response.json()[0]["products"]], [39, 45])
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email = ?", (owner_email,))


if __name__ == "__main__":
    unittest.main()
