from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class StaticAdvancedToggleTests(unittest.TestCase):
    def test_advanced_settings_use_explicit_toggle_button(self) -> None:
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="advanced-toggle"', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('id="advanced-panel"', html)
        self.assertIn("hidden", html)
        self.assertIn('/static/app.js?v=', html)
        self.assertIn('/static/styles.css?v=', html)
        self.assertIn("advanced-toggle", js)
        self.assertIn("aria-expanded", js)


if __name__ == "__main__":
    unittest.main()
