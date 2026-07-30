from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlparse

from app.url_safety import UnsafeUrlError, validate_public_http_url


@dataclass
class RenderedPage:
    url: str
    html: str
    text: str
    status_code: int | None = None
    screenshot_png: bytes | None = None


class RenderUnavailableError(RuntimeError):
    pass


async def render_page(url: str, selector: str | None = None, wait_ms: int = 1200) -> RenderedPage | None:
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RenderUnavailableError("Playwright is not installed") from exc

    try:
        safe_url = validate_public_http_url(url)
    except UnsafeUrlError:
        return None

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent="Mozilla/5.0 ProductIntelligenceMonitor/1.0 (+browser render worker)",
                viewport={"width": 1365, "height": 900},
                java_script_enabled=True,
            )
            page = await context.new_page()

            async def guard_request(route, request) -> None:
                parsed = urlparse(request.url)
                if parsed.scheme in {"http", "https"}:
                    try:
                        validate_public_http_url(request.url)
                    except UnsafeUrlError:
                        await route.abort()
                        return
                elif parsed.scheme not in {"data", "blob", "about"}:
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", guard_request)
            response = await page.goto(safe_url, wait_until="domcontentloaded", timeout=15000)
            try:
                validate_public_http_url(page.url)
            except UnsafeUrlError:
                return None
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            if selector:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                except PlaywrightTimeoutError:
                    pass
            if wait_ms > 0:
                await asyncio.sleep(wait_ms / 1000)
            html = await page.content()
            if selector:
                try:
                    text = await page.locator(selector).first.inner_text(timeout=3000)
                except PlaywrightError:
                    text = await page.locator("body").inner_text(timeout=3000)
            else:
                text = await page.locator("body").inner_text(timeout=3000)
            screenshot_png = await page.screenshot(type="png", full_page=True)
            return RenderedPage(
                url=page.url,
                html=html,
                text=text,
                status_code=response.status if response else None,
                screenshot_png=screenshot_png,
            )
        finally:
            await browser.close()


async def try_render_page(url: str, selector: str | None = None, wait_ms: int = 1200) -> RenderedPage | None:
    try:
        return await render_page(url, selector=selector, wait_ms=wait_ms)
    except (RenderUnavailableError, Exception):
        return None
