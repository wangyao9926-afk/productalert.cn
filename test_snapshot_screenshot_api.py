from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db import execute_sql, get_db, init_db, insert_row, update_by_id
from app.evidence_store import evidence_path, save_screenshot
from app.main import app
from test_visual_evidence import png_for_pixel


class SnapshotScreenshotApiTests(unittest.TestCase):
    def test_only_the_site_owner_can_download_saved_screenshot(self) -> None:
        init_db()
        marker = uuid4().hex
        owner_email = f"screenshot-owner-{marker}@monitor.internal"
        stranger_email = f"screenshot-stranger-{marker}@monitor.internal"
        screenshot_path: str | None = None
        client = TestClient(app)

        try:
            owner = client.post("/api/auth/register", json={"email": owner_email, "password": "test-password-123"})
            stranger = client.post("/api/auth/register", json={"email": stranger_email, "password": "test-password-123"})
            self.assertEqual(owner.status_code, 200, owner.text)
            self.assertEqual(stranger.status_code, 200, stranger.text)
            owner_headers = {"Authorization": f"Bearer {owner.json()['token']}"}
            stranger_headers = {"Authorization": f"Bearer {stranger.json()['token']}"}

            with get_db() as db:
                site_id = insert_row(
                    db,
                    "sites",
                    {
                        "user_id": owner.json()["user"]["id"],
                        "name": "Screenshot owner test",
                        "url": f"https://owner-{marker}.example.com",
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
                        "url": f"https://owner-{marker}.example.com/new",
                        "scan_interval_minutes": 60,
                    },
                )
                snapshot_id = insert_row(
                    db,
                    "source_snapshots",
                    {
                        "source_id": source_id,
                        "url": f"https://owner-{marker}.example.com/new",
                        "content_hash": "content-hash",
                        "text_hash": "text-hash",
                        "screenshot_hash": "screenshot-hash",
                    },
                )
                screenshot_path = save_screenshot(source_id, snapshot_id, png_for_pixel(255, 255, 255))
                update_by_id(db, "source_snapshots", snapshot_id, {"screenshot_path": screenshot_path})

            owner_image = client.get(f"/api/source-snapshots/{snapshot_id}/screenshot", headers=owner_headers)
            stranger_image = client.get(f"/api/source-snapshots/{snapshot_id}/screenshot", headers=stranger_headers)
            self.assertEqual(owner_image.status_code, 200, owner_image.text)
            self.assertEqual(owner_image.headers["content-type"], "image/png")
            self.assertEqual(stranger_image.status_code, 404, stranger_image.text)
        finally:
            with get_db() as db:
                execute_sql(db, "DELETE FROM users WHERE email IN (?, ?)", (owner_email, stranger_email))
            if screenshot_path:
                stored_file = evidence_path(screenshot_path)
                if stored_file.is_file():
                    stored_file.unlink()
                if stored_file.parent.is_dir() and not any(stored_file.parent.iterdir()):
                    stored_file.parent.rmdir()


if __name__ == "__main__":
    unittest.main()
