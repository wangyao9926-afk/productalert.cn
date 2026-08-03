from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.notifier import change_event_payload


class NotificationEvidenceLinkTests(unittest.TestCase):
    def test_configured_public_url_adds_normalized_change_detail_link(self) -> None:
        event = {"id": 42, "change_type": "price_change", "summary": "Price changed"}
        with patch.dict(os.environ, {"APP_PUBLIC_URL": "https://app.example.com/"}):
            payload = change_event_payload(event)

        self.assertEqual(payload["evidence_url"], "https://app.example.com/changes/42")
        self.assertIn("https://app.example.com/changes/42", payload["text"]["content"])

    def test_unset_public_url_omits_evidence_link(self) -> None:
        event = {"id": 42, "change_type": "price_change", "summary": "Price changed"}
        with patch.dict(os.environ, {}, clear=True):
            payload = change_event_payload(event)

        self.assertNotIn("evidence_url", payload)


if __name__ == "__main__":
    unittest.main()
