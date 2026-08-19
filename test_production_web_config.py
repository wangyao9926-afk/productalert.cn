from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.settings import production_web_configuration_errors, web_security_settings


class ProductionWebConfigurationTests(unittest.TestCase):
    def test_production_environment_template_declares_required_web_boundary_settings(self) -> None:
        template = (Path(__file__).resolve().parent / ".env.production.example").read_text(encoding="utf-8")

        self.assertIn("APP_ENV=production", template)
        self.assertIn("APP_PUBLIC_URL=https://<your-api-domain>", template)
        self.assertIn("CORS_ALLOWED_ORIGINS=https://<your-frontend-domain>", template)
        self.assertIn("SESSION_COOKIE_SECURE=true", template)
        self.assertIn("SESSION_COOKIE_SAMESITE=none", template)

    def test_production_config_check_rejects_missing_public_web_boundary(self) -> None:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".env", delete=False) as handle:
            handle.write(
                "DATABASE_URL=postgresql://user:password@db.example.com:5432/product_monitor\n"
                "QUEUE_BACKEND=rq\n"
                "REDIS_URL=redis://redis.example.com:6379/0\n"
                "START_BACKGROUND_WORKERS=false\n"
                "START_NOTIFICATION_WORKER=false\n"
                "SESSION_COOKIE_SECURE=true\n"
            )
            env_path = handle.name
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(Path(__file__).resolve().parent / "check-production-config.ps1"),
                    "-EnvPath",
                    env_path,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            os.unlink(env_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("APP_ENV must be production", result.stdout)
        self.assertIn("CORS_ALLOWED_ORIGINS must list", result.stdout)
        self.assertIn("SESSION_COOKIE_SAMESITE must be none", result.stdout)

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
