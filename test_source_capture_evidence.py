from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.crawler import extract_source_text
from app.render_worker import RenderedPage


class SourceCaptureEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_capture_preserves_response_evidence(self) -> None:
        response = SimpleNamespace(
            url="https://example.com/new-arrivals",
            content=(
                "<html><body><h1>New arrivals</h1><p>"
                + ("Product catalog update with verified launch details. " * 8)
                + "</p></body></html>"
            ),
            status_code=200,
            content_type="text/html; charset=utf-8",
        )
        with patch("app.crawler.fetch_document", new=AsyncMock(return_value=response)):
            captured = await extract_source_text("https://example.com/new-arrivals")

        self.assertIsNotNone(captured)
        assert captured is not None
        self.assertEqual(captured.url, response.url)
        self.assertEqual(captured.capture_method, "http")
        self.assertEqual(captured.http_status, 200)
        self.assertEqual(captured.content_type, "text/html; charset=utf-8")
        self.assertEqual(captured.content_length, len(response.content.encode("utf-8")))

    async def test_sparse_http_page_uses_browser_render_and_records_that_method(self) -> None:
        response = SimpleNamespace(
            url="https://example.com/new-arrivals",
            content="<html><body>Loading</body></html>",
            status_code=200,
            content_type="text/html",
        )
        rendered = RenderedPage(
            url="https://example.com/new-arrivals",
            html="<html><body><h1>New collection</h1><p>Product one is now available with complete launch information.</p></body></html>",
            text="New collection Product one is now available with complete launch information.",
            status_code=202,
        )
        with (
            patch("app.crawler.fetch_document", new=AsyncMock(return_value=response)),
            patch("app.crawler.try_render_page", new=AsyncMock(return_value=rendered)),
        ):
            captured = await extract_source_text("https://example.com/new-arrivals")

        self.assertIsNotNone(captured)
        assert captured is not None
        self.assertEqual(captured.capture_method, "browser_render")
        self.assertIn("New collection", captured.text)
        self.assertEqual(captured.http_status, 202)


if __name__ == "__main__":
    unittest.main()
