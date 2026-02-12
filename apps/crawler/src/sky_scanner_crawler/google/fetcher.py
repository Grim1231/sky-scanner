"""Fetch Google Flights pages using primp (with Playwright fallback)."""

from __future__ import annotations

import asyncio
import logging

from sky_scanner_crawler.config import settings

logger = logging.getLogger(__name__)

GOOGLE_FLIGHTS_URL = "https://www.google.com/travel/flights"


def _sync_fetch(
    params: dict[str, str],
    cookies: dict[str, str],
    proxy_url: str,
    timeout: int,
) -> str:
    """Synchronous fetch using primp Client (run inside asyncio.to_thread)."""
    from primp import Client  # type: ignore[import-untyped]

    client_kwargs: dict[str, object] = {
        "impersonate": "chrome_126",
        "verify": False,
        "timeout": timeout,
    }
    if proxy_url:
        client_kwargs["proxy"] = proxy_url

    client = Client(**client_kwargs)  # type: ignore[arg-type]
    res = client.get(GOOGLE_FLIGHTS_URL, params=params, cookies=cookies)
    if res.status_code != 200:
        msg = f"Google Flights returned HTTP {res.status_code}"
        raise RuntimeError(msg)
    return res.text


async def _playwright_fetch(
    params: dict[str, str],
    cookies: dict[str, str],
) -> str:
    """Fallback fetch using Playwright headless Chromium."""
    from playwright.async_api import async_playwright

    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{GOOGLE_FLIGHTS_URL}?{query}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        if cookies:
            cookie_list = [
                {
                    "name": k,
                    "value": v,
                    "domain": ".google.com",
                    "path": "/",
                }
                for k, v in cookies.items()
            ]
            await context.add_cookies(cookie_list)  # type: ignore[arg-type]
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        html = await page.content()
        await browser.close()
    return html


async def fetch_flights_page(
    params: dict[str, str],
    cookies: dict[str, str],
) -> str:
    """Fetch a Google Flights page. Tries primp first, falls back to Playwright."""
    proxy_url = settings.l1_proxy_url
    timeout = settings.l1_timeout

    try:
        return await asyncio.to_thread(_sync_fetch, params, cookies, proxy_url, timeout)
    except Exception:
        logger.warning("primp fetch failed, falling back to Playwright")
        try:
            return await _playwright_fetch(params, cookies)
        except Exception:
            logger.exception("Playwright fallback also failed")
            raise
