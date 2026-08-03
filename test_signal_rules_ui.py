from __future__ import annotations

import unittest
from pathlib import Path


class SignalRulesUiTests(unittest.TestCase):
    def test_notification_rules_expose_price_and_stock_conditions(self) -> None:
        api_source = Path("frontend/src/api/notifications.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/notifications/NotificationsPage.tsx").read_text(encoding="utf-8")

        self.assertIn("max_price_amount", api_source)
        self.assertIn("require_in_stock", api_source)
        self.assertIn("价格上限", page_source)
        self.assertIn("仅在有货时通知", page_source)


if __name__ == "__main__":
    unittest.main()
