"""HTTP client for the Kiwi Tequila search API."""

from __future__ import annotations

import logging

import httpx

from sky_scanner_crawler.config import settings
from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.tequila.kiwi.com"


class KiwiClient:
    """Thin async wrapper around the Kiwi Tequila ``/v2/search`` endpoint."""

    def __init__(self, *, api_key: str | None = None, timeout: int = 30) -> None:
        key = api_key or settings.kiwi_api_key
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"apikey": key},
            timeout=httpx.Timeout(timeout),
        )

    # Retry on transient HTTP / connection errors
    @async_retry(
        max_retries=3,
        base_delay=1.0,
        max_delay=30.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def search_flights(self, params: dict[str, object]) -> dict:
        """Call ``GET /v2/search`` and return the parsed JSON body."""
        resp = await self._client.get("/v2/search", params=params)
        resp.raise_for_status()
        data: dict = resp.json()
        logger.debug(
            "Kiwi search returned %d results",
            len(data.get("data", [])),
        )
        return data

    async def close(self) -> None:
        """Shut down the underlying HTTPX client."""
        await self._client.aclose()
