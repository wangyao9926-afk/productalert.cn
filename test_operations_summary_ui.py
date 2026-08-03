from __future__ import annotations

import unittest
from pathlib import Path


class OperationsSummaryUiTests(unittest.TestCase):
    def test_operations_center_uses_server_calculated_observability_summary(self) -> None:
        api_source = Path("frontend/src/api/operations.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/operations/OperationsPage.tsx").read_text(encoding="utf-8")

        self.assertIn('getJson<OperationsSummary>("/api/operations/summary")', api_source)
        self.assertIn("summary: OperationsSummary", api_source)
        self.assertIn("context?.summary", page_source)
        self.assertIn("notificationStatus.failed", page_source)
        self.assertIn("failure_categories", page_source)
        self.assertIn("queue: queueSummary(scanJobs)", page_source)


if __name__ == "__main__":
    unittest.main()
