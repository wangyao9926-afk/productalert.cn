from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class StaticMonitorSettingsUiTests(unittest.TestCase):
    def test_sources_view_exposes_persistent_edit_controls_and_feedback(self) -> None:
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("renderSiteSettingsForm(site)", js)
        self.assertIn('class="site-settings-form"', js)
        self.assertIn('data-action="save-site-settings"', js)
        self.assertIn('class="source-edit-form"', js)
        self.assertIn('data-action="save-source"', js)
        self.assertIn("showFeedback", js)
        self.assertIn("保存成功", js)
        self.assertIn("input.checked = selectedSet.has(input.value)", js)


if __name__ == "__main__":
    unittest.main()
