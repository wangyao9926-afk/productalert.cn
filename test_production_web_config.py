from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.settings import production_web_configuration_errors, web_security_settings


class ProductionWebConfigurationTests(unittest.TestCase):
    def test_production_settings_accept_explicit_https_frontend_and_cross_site_cookie(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://productalert.netlify.app,https://app.productalert.cn",
                "SESSION_COOKIE_SECURE": "true",
                "SESSION_COOKIE_SAMESITE": "none",
            },
            clear=False,
        ):
            settings = web_security_settings()

        self.assertEqual(settings.allowed_origins, ("https://productalert.netlify.app", "https://app.productalert.cn"))
        self.assertTrue(settings.session_cookie_secure)
        self.assertEqual(settings.session_cookie_samesite, "none")
        self.assertEqual(production_web_configuration_errors(settings), [])

    def test_local_frontend_origin_receives_credentialed_cors_preflight(self) -> None:
        client = TestClient(app)
        response = client.options(
            "/api/system/ping",
            headers={
                "Origin": "http://127.0.0.1:4175",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://127.0.0.1:4175")
        self.assertEqual(response.headers.get("access-control-allow-credentials"), "true")


if __name__ == "__main__":
    unittest.main()
