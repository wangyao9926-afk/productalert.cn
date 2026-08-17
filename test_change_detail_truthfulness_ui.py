from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class ChangeDetailTruthfulnessUiTests(unittest.TestCase):
    def test_detail_page_does_not_invent_price_or_stock_evidence_when_a_snapshot_is_missing(self) -> None:
        page = (ROOT / "frontend" / "src" / "features" / "changes" / "ChangeDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn("尚未记录可核对的前后值", page)
        self.assertIn('return "待核验"', page)
        self.assertNotIn('before: "¥450"', page)
        self.assertNotIn('after: "¥475"', page)
        self.assertNotIn('before: "售罄"', page)


if __name__ == "__main__":
    unittest.main()
