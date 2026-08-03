from __future__ import annotations

import unittest
from pathlib import Path


class EventSuppressionUiTests(unittest.TestCase):
    def test_change_detail_exposes_explicit_same_source_suppression_action(self) -> None:
        api_source = Path("frontend/src/api/changes.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/changes/ChangeDetailPage.tsx").read_text(encoding="utf-8")

        self.assertIn("suppressSimilarChangeEvents", api_source)
        self.assertIn("/api/change-events/${eventId}/suppress-similar", api_source)
        self.assertIn("suppressSimilarChangeEvents", page_source)
        self.assertIn("忽略此来源同类变化", page_source)


if __name__ == "__main__":
    unittest.main()
