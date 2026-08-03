from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.crawler import ExtractedSourceText
from app.db import execute_sql, fetchone, get_db, init_db, insert_row, row_to_dict
from app.monitor import capture_source_snapshot


class SnapshotEvidencePersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_persists_capture_evidence(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        source_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": 1,
                        "name": "Evidence test",
                        "url": f"https://evidence-{marker}.example.com",
                        "scan_interval_minutes": 60,
                        "notification_events": "[\"product_new\"]",
                    },
                )
                source_id = insert_row(
                    db,
                    "monitor_sources",
                    {
                        "site_id": site_id,
                        "source_type": "custom_page",
                        "url": f"https://evidence-{marker}.example.com/new",
                        "scan_interval_minutes": 60,
                    },
                )

            extracted = ExtractedSourceText(
                url=f"https://evidence-{marker}.example.com/final",
                selector="main",
                text="Verified product catalog text",
                content_hash="content-hash",
                text_hash="text-hash",
                capture_method="browser_render",
                http_status=200,
                content_type="text/html",
                content_length=2468,
            )
            source_data = {
                "id": source_id,
                "site_id": site_id,
                "url": f"https://evidence-{marker}.example.com/new",
                "selector": "main",
            }
            with patch("app.monitor.extract_source_text", new=AsyncMock(return_value=extracted)):
                result = await capture_source_snapshot(source_data, baseline_mode=True, notify=False)

            self.assertIsNotNone(result)
            assert result is not None
            with get_db() as db:
                snapshot = fetchone(db, "SELECT * FROM source_snapshots WHERE id = ?", (result["snapshot_id"],))
            saved = row_to_dict(snapshot)
            self.assertEqual(saved["url"], extracted.url)
            self.assertEqual(saved["capture_method"], "browser_render")
            self.assertEqual(saved["http_status"], 200)
            self.assertEqual(saved["content_type"], "text/html")
            self.assertEqual(saved["content_length"], 2468)
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


if __name__ == "__main__":
    unittest.main()
