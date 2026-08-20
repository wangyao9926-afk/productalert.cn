from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.business_data_export import export_business_data, write_business_data_export


class BusinessDataExportTests(unittest.TestCase):
    def test_export_keeps_monitoring_baseline_and_excludes_credentials_and_webhooks(self) -> None:
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, password_hash TEXT);
            CREATE TABLE sites (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, url TEXT, scan_interval_minutes INTEGER, webhook_url TEXT, enabled INTEGER, category TEXT, priority INTEGER, notes TEXT, notification_events_json TEXT, created_at TEXT, last_checked_at TEXT, last_status TEXT);
            CREATE TABLE monitor_sources (id INTEGER PRIMARY KEY, site_id INTEGER, url TEXT);
            CREATE TABLE known_urls (id INTEGER PRIMARY KEY, source_id INTEGER, url TEXT);
            CREATE TABLE products (id INTEGER PRIMARY KEY, site_id INTEGER, source_id INTEGER, title TEXT, url TEXT, features_json TEXT);
            CREATE TABLE product_variants (id INTEGER PRIMARY KEY, product_id INTEGER, external_id TEXT);
            CREATE TABLE product_identifiers (id INTEGER PRIMARY KEY, product_id INTEGER, identifier_type TEXT, normalized_value TEXT);
            CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id INTEGER);
            CREATE TABLE notification_rules (id INTEGER PRIMARY KEY, user_id INTEGER, target_url TEXT);
            """
        )
        source.execute("INSERT INTO users VALUES (7, 'owner@example.com', 'password-hash')")
        source.execute("INSERT INTO sites VALUES (11, 7, 'Brand', 'https://brand.example', 60, 'https://hooks.example/secret', 1, NULL, 2, NULL, '[\"product_new\"]', '2026-08-20T00:00:00+00:00', NULL, NULL)")
        source.execute("INSERT INTO monitor_sources VALUES (12, 11, 'https://brand.example/collections/all')")
        source.execute("INSERT INTO known_urls VALUES (13, 12, 'https://brand.example/products/new')")
        source.execute("INSERT INTO products VALUES (14, 11, 12, 'New Product', 'https://brand.example/products/new', '[\"feature\"]')")
        source.execute("INSERT INTO product_variants VALUES (15, 14, 'variant-1')")
        source.execute("INSERT INTO product_identifiers VALUES (16, 14, 'sku', 'SKU-1')")
        source.execute("INSERT INTO sessions VALUES ('session-token', 7)")
        source.execute("INSERT INTO notification_rules VALUES (17, 7, 'https://hooks.example/secret')")

        package = export_business_data(source, user_id=7)
        serialized = json.dumps(package, ensure_ascii=False)

        self.assertEqual(package["version"], 1)
        self.assertEqual(package["tables"]["sites"][0]["url"], "https://brand.example")
        self.assertNotIn("webhook_url", package["tables"]["sites"][0])
        self.assertEqual(package["tables"]["products"][0]["title"], "New Product")
        self.assertEqual(package["counts"], {"sites": 1, "monitor_sources": 1, "known_urls": 1, "products": 1, "product_variants": 1, "product_identifiers": 1})
        self.assertNotIn("users", package["tables"])
        self.assertNotIn("sessions", package["tables"])
        self.assertNotIn("notification_rules", package["tables"])
        self.assertNotIn("password-hash", serialized)
        self.assertNotIn("session-token", serialized)
        self.assertNotIn("hooks.example", serialized)

    def test_writer_creates_a_portable_json_package(self) -> None:
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        source.execute("CREATE TABLE sites (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, url TEXT, scan_interval_minutes INTEGER, webhook_url TEXT, enabled INTEGER, category TEXT, priority INTEGER, notes TEXT, notification_events_json TEXT, created_at TEXT, last_checked_at TEXT, last_status TEXT)")
        source.execute("INSERT INTO sites VALUES (1, 9, 'Brand', 'https://brand.example', 60, 'https://hooks.example/secret', 1, NULL, 2, NULL, '[\"product_new\"]', '2026-08-20T00:00:00+00:00', NULL, NULL)")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "exports" / "business-data.json"
            written = write_business_data_export(source, user_id=9, output_path=output)

            self.assertEqual(written, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["counts"]["sites"], 1)


if __name__ == "__main__":
    unittest.main()
