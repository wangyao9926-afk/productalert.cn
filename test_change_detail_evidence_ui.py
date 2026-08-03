from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ChangeDetailEvidenceUiTests(unittest.TestCase):
    def test_detail_page_displays_and_links_to_the_captured_final_url(self) -> None:
        page = (ROOT / "frontend" / "src" / "features" / "changes" / "ChangeDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn("const sourceEvidenceUrl = captureEvidence?.url", page)
        self.assertIn("最终 URL", page)
        self.assertIn('href={sourceEvidenceUrl}', page)


if __name__ == "__main__":
    unittest.main()
