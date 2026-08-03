from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.crawler import ExtractedSourceText
from app.db import execute_sql, fetchone, get_db, init_db, insert_row, row_to_dict
from app.evidence_store import save_screenshot
from app.monitor import capture_source_snapshot
from app.render_worker import RenderedPage
from test_visual_evidence import png_for_pixel


class SnapshotVisualEvidenceTests(unittest.TestCase):
    def test_saved_screenshot_uses_private_source_and_snapshot_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            private_root = Path(temporary_directory)
            with patch("app.evidence_store.EVIDENCE_DIR", private_root):
                relative_path = save_screenshot(source_id=12, snapshot_id=34, png=b"png-evidence")

            self.assertEqual(relative_path, "source-12/snapshot-34.png")
            self.assertEqual((private_root / relative_path).read_bytes(), b"png-evidence")


class SnapshotVisualCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_baseline_snapshot_persists_rendered_png_metadata(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": 1,
                        "name": "Visual evidence test",
                        "url": f"https://visual-{marker}.example.com",
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
                        "url": f"https://visual-{marker}.example.com/new",
                        "scan_interval_minutes": 60,
                    },
                )

            extracted = ExtractedSourceText(
                url=f"https://visual-{marker}.example.com/new",
                selector=None,
                text="baseline page text",
                content_hash="content-hash",
                text_hash="text-hash",
                capture_method="http",
                http_status=200,
                content_type="text/html",
                content_length=18,
            )
            rendered = RenderedPage(
                url=extracted.url,
                html="<html><body>baseline page text</body></html>",
                text=extracted.text,
                status_code=200,
                screenshot_png=png_for_pixel(255, 255, 255),
            )
            source_data = {"id": source_id, "site_id": site_id, "url": extracted.url, "selector": None}
            with tempfile.TemporaryDirectory() as temporary_directory:
                with (
                    patch("app.monitor.extract_source_text", new=AsyncMock(return_value=extracted)),
                    patch("app.monitor.try_render_page", new=AsyncMock(return_value=rendered), create=True),
                    patch("app.evidence_store.EVIDENCE_DIR", Path(temporary_directory)),
                ):
                    result = await capture_source_snapshot(source_data, baseline_mode=True, notify=False)

                with get_db() as db:
                    snapshot = row_to_dict(fetchone(db, "SELECT * FROM source_snapshots WHERE id = ?", (result["snapshot_id"],)))
                self.assertTrue(snapshot["screenshot_path"])
                self.assertTrue(snapshot["screenshot_hash"])
                self.assertEqual(snapshot["visual_change_ratio"], None)
                self.assertTrue((Path(temporary_directory) / snapshot["screenshot_path"]).is_file())
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))

    async def test_changed_screenshot_is_saved_but_identical_follow_up_is_not(self) -> None:
        init_db()
        marker = uuid4().hex
        site_id: int | None = None
        try:
            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": 1,
                        "name": "Visual dedupe test",
                        "url": f"https://visual-dedupe-{marker}.example.com",
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
                        "url": f"https://visual-dedupe-{marker}.example.com/new",
                        "scan_interval_minutes": 60,
                    },
                )

            url = f"https://visual-dedupe-{marker}.example.com/new"
            baseline = ExtractedSourceText(url, None, "baseline", "content-one", "text-one", "http", 200, "text/html", 8)
            visual_only = ExtractedSourceText(url, None, "baseline", "content-one", "text-one", "http", 200, "text/html", 8)
            white = RenderedPage(url, "<body>baseline</body>", "baseline", 200, png_for_pixel(255, 255, 255))
            black = RenderedPage(url, "<body>changed</body>", "changed", 200, png_for_pixel(0, 0, 0))
            source_data = {"id": source_id, "site_id": site_id, "url": url, "selector": None}
            with tempfile.TemporaryDirectory() as temporary_directory:
                with (
                    patch("app.monitor.extract_source_text", new=AsyncMock(side_effect=[baseline, visual_only, visual_only, visual_only])),
                    patch("app.monitor.try_render_page", new=AsyncMock(side_effect=[white, black, black, white])),
                    patch("app.evidence_store.EVIDENCE_DIR", Path(temporary_directory)),
                ):
                    first = await capture_source_snapshot(source_data, baseline_mode=True, notify=False)
                    second = await capture_source_snapshot(source_data, baseline_mode=False, notify=False)
                    third = await capture_source_snapshot(source_data, baseline_mode=False, notify=False)
                    fourth = await capture_source_snapshot(source_data, baseline_mode=False, notify=False)

                with get_db() as db:
                    changed_snapshot = row_to_dict(fetchone(db, "SELECT * FROM source_snapshots WHERE id = ?", (second["snapshot_id"],)))
                    duplicate_snapshot = row_to_dict(fetchone(db, "SELECT * FROM source_snapshots WHERE id = ?", (third["snapshot_id"],)))
                    visual_event_row = fetchone(db, "SELECT * FROM change_events WHERE snapshot_after_id = ?", (second["snapshot_id"],))
                    follow_up_visual_event_row = fetchone(db, "SELECT * FROM change_events WHERE snapshot_after_id = ?", (fourth["snapshot_id"],))
                self.assertTrue(first["screenshot_saved"])
                self.assertTrue(second["screenshot_saved"])
                self.assertTrue(second["changed"])
                self.assertEqual(changed_snapshot["visual_change_ratio"], 1.0)
                self.assertTrue(changed_snapshot["screenshot_path"])
                self.assertIsNotNone(visual_event_row)
                assert visual_event_row is not None
                visual_event = row_to_dict(visual_event_row)
                self.assertEqual(visual_event["change_type"], "visual_change")
                self.assertFalse(third["screenshot_saved"])
                self.assertIsNone(duplicate_snapshot["screenshot_path"])
                self.assertTrue(fourth["screenshot_saved"])
                self.assertIsNotNone(follow_up_visual_event_row)
                assert follow_up_visual_event_row is not None
                follow_up_visual_event = row_to_dict(follow_up_visual_event_row)
                self.assertEqual(follow_up_visual_event["snapshot_before_id"], second["snapshot_id"])
                self.assertEqual(len(list(Path(temporary_directory).rglob("*.png"))), 3)
        finally:
            if site_id is not None:
                with get_db() as db:
                    execute_sql(db, "DELETE FROM sites WHERE id = ?", (site_id,))


if __name__ == "__main__":
    unittest.main()
