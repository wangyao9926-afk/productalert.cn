from __future__ import annotations

import unittest
from uuid import uuid4

from app.crawler import ProductCandidate
from app.db import execute_sql, fetchall, get_db, init_db, insert_row, json_dumps, row_to_dict
from app.monitor import extract_and_store_product


class ProductIdentityReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_platform_product_id_updates_an_existing_product_after_its_url_changes(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        old_url = f"https://identity-reconcile-{marker}.example.com/products/trail-pack"
        new_url = f"https://identity-reconcile-{marker}.example.com/products/trail-pack-2026"
        try:
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": 1,
                        "name": "Identity reconciliation site",
                        "url": f"https://identity-reconcile-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": json_dumps(["product_new", "price_change"]),
                    },
                )
                source_id = insert_row(
                    db,
                    "monitor_sources",
                    {
                        "site_id": site_id,
                        "source_type": "listing_page",
                        "url": f"https://identity-reconcile-{marker}.example.com/collections/all",
                        "scan_interval_minutes": 60,
                    },
                )

            source_data = {"id": source_id, "site_id": site_id, "site_name": "Identity reconciliation site", "url": old_url}
            baseline = ProductCandidate(
                url=old_url,
                payload={"kind": "shopify_product", "product": {"id": 501, "title": "Trail Pack", "variants": [{"id": 101, "sku": "TRAIL-42", "price": "39.00", "available": True}]}},
            )
            moved = ProductCandidate(
                url=new_url,
                payload={"kind": "shopify_product", "product": {"id": 501, "title": "Trail Pack", "variants": [{"id": 101, "sku": "TRAIL-42", "price": "42.00", "available": True}]}},
            )

            await extract_and_store_product(baseline, source_data, source_id, discovery_status="baseline", notify=False, record_changes=False)
            _, outcome = await extract_and_store_product(moved, source_data, source_id, discovery_status="known", notify=False, record_changes=True)

            with get_db() as db:
                products = [row_to_dict(row) for row in fetchall(db, "SELECT * FROM products WHERE site_id = ?", (site_id,))]
            self.assertEqual(outcome, "existing")
            self.assertEqual(len(products), 1)
            self.assertEqual(products[0]["url"], new_url)
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


if __name__ == "__main__":
    unittest.main()
