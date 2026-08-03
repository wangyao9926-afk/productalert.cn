from __future__ import annotations

import unittest
from pathlib import Path


class FrontendDeploymentConfigurationTests(unittest.TestCase):
    def test_frontend_api_client_supports_a_deployed_api_base_url(self) -> None:
        source = Path("frontend/src/api/client.ts").read_text(encoding="utf-8")
        example = Path("frontend/.env.example").read_text(encoding="utf-8")

        self.assertIn("VITE_API_BASE_URL", source)
        self.assertIn("apiUrl(path)", source)
        self.assertIn("VITE_API_BASE_URL", example)

    def test_production_can_disable_demo_data_fallback(self) -> None:
        source = Path("frontend/src/api/overview.ts").read_text(encoding="utf-8")

        self.assertIn("VITE_ENABLE_DEMO_FALLBACK", source)
        self.assertIn('mode: "unavailable"', source)


if __name__ == "__main__":
    unittest.main()
