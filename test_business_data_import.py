from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from app.business_data_export import export_business_data
from app.business_data_import import database_row_id, import_business_data, read_business_data_package


def create_schema(db: sqlite3.Connection) -> None:
    for migration in sorted(Path("app/migrations/sqlite").glob("*.sql")):
        db.executescript(migration.read_text(encoding="utf-8"))


class BusinessDataImportTests(unittest.TestCase):
    def test_import_command_exposes_required_operator_inputs(self) -> None:
        result = subprocess.run(
            [sys.executable, "import_business_data.py", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--package", result.stdout)
        self.assertIn("--target-user-id", result.stdout)

    def test_database_row_id_supports_postgresql_dictionary_rows(self) -> None:
        self.assertEqual(database_row_id({"id": 27}), 27)

    def test_reader_loads_the_portable_json_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package_path = Path(directory) / "business-data.json"
            package_path.write_text('{"version": 1, "tables": {}, "counts": {}}', encoding="utf-8")

            self.assertEqual(read_business_data_package(package_path)["version"], 1)

    def test_import_rebuilds_a_monitoring_baseline_for_a_new_owner(self) -> None:
        source = sqlite3.connect(":memory:")
        source.row_factory = sqlite3.Row
        create_schema(source)
        source.execute("INSERT INTO users (id, email, password_hash) VALUES (84, 'old@example.com', 'hash')")
        source.execute("INSERT INTO sites (id, user_id, name, url, scan_interval_minutes, notification_events_json) VALUES (11, 84, 'Brand', 'https://brand.example', 60, '[\"product_new\"]')")
        source.execute("INSERT INTO monitor_sources (id, site_id, source_type, url) VALUES (12, 11, 'homepage', 'https://brand.example')")
        source.execute("INSERT INTO known_urls (id, source_id, url) VALUES (13, 12, 'https://brand.example/products/new')")
        source.execute("INSERT INTO products (id, site_id, source_id, url, title, content_hash) VALUES (14, 11, 12, 'https://brand.example/products/new', 'New Product', 'content-hash')")
        source.execute("INSERT INTO product_variants (id, product_id, external_id) VALUES (15, 14, 'variant-1')")
        source.execute("INSERT INTO product_identifiers (id, product_id, identifier_type, normalized_value, raw_value, provenance) VALUES (16, 14, 'sku', 'SKU-1', 'SKU-1', 'json_ld')")
        package = export_business_data(source, user_id=84)

        target = sqlite3.connect(":memory:")
        target.row_factory = sqlite3.Row
        create_schema(target)
        target.execute("INSERT INTO users (id, email, password_hash) VALUES (9, 'new@example.com', 'new-hash')")

        result = import_business_data(target, package, target_user_id=9)
        repeated_result = import_business_data(target, package, target_user_id=9)

        self.assertEqual(result, {"sites": 1, "monitor_sources": 1, "known_urls": 1, "products": 1, "product_variants": 1, "product_identifiers": 1})
        self.assertEqual(repeated_result, result)
        self.assertEqual(tuple(target.execute("SELECT user_id, url FROM sites").fetchone()), (9, "https://brand.example"))
        self.assertEqual(
            json.loads(target.execute("SELECT notification_events_json FROM sites").fetchone()[0]),
            ["product_new"],
        )
        self.assertEqual(target.execute("SELECT COUNT(*) FROM sites").fetchone()[0], 1)
        self.assertEqual(target.execute("SELECT COUNT(*) FROM monitor_sources").fetchone()[0], 1)
        self.assertEqual(target.execute("SELECT COUNT(*) FROM known_urls").fetchone()[0], 1)
        self.assertEqual(target.execute("SELECT COUNT(*) FROM products").fetchone()[0], 1)
        self.assertEqual(target.execute("SELECT COUNT(*) FROM product_variants").fetchone()[0], 1)
        self.assertEqual(target.execute("SELECT COUNT(*) FROM product_identifiers").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
