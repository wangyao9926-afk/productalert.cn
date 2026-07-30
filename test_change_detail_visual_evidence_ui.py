from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ChangeDetailVisualEvidenceUiTests(unittest.TestCase):
    def test_change_detail_renders_real_snapshot_images_and_missing_evidence_reason(self) -> None:
        page = (ROOT / "frontend" / "src" / "features" / "changes" / "ChangeDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn("snapshot_before?.screenshot_url", page)
        self.assertIn("snapshot_after?.screenshot_url", page)
        self.assertIn("screenshot_error", page)
        self.assertNotIn("真实截图服务接入后显示页面快照", page)


if __name__ == "__main__":
    unittest.main()
