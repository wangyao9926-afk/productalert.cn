from __future__ import annotations

import unittest
from pathlib import Path


class NotificationRulesUiTests(unittest.TestCase):
    def test_notification_page_can_create_robot_delivery_rules(self) -> None:
        api_source = Path("frontend/src/api/notifications.ts").read_text(encoding="utf-8")
        page_source = Path("frontend/src/features/notifications/NotificationsPage.tsx").read_text(encoding="utf-8")

        self.assertIn("createNotificationRule", api_source)
        self.assertIn("新建推送规则", page_source)
        self.assertIn("企业微信", page_source)
        self.assertIn("飞书", page_source)


if __name__ == "__main__":
    unittest.main()
