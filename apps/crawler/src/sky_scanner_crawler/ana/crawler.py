"""ANA (NH) L3 crawler -- Playwright-based international flight search."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import AnaPlaywrightClient
from .response_parser import parse_api_responses, parse_dom_flights

logger = logging.getLogger(__name__)


class AnaCrawler(BaseCrawler):
    """L3 crawler: ANA international flight search via Playwright.

    Automates ANA's booking search form at ``ana.co.jp/en/jp/international/``
    to retrieve flight schedules and fares.  Uses Playwright to bypass
    Akamai Bot Manager protection.

    Returns ``NormalizedFlight`` objects extracted from:
    1. Intercepted API JSON responses from ``aswbe.ana.co.jp``
    2. DOM-scraped flight result cards (fallback)
    """

    def __init__(self) -> None:
        self._client = AnaPlaywrightClient(timeout=60)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Execute a search and return normalized results."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.search_flights(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
            )

            # Parse API responses first (higher quality).
            flights = parse_api_responses(
                raw.get("api_responses", []),
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date.isoformat(),
                cabin_class=req.cabin_class,
            )

            # If no API flights, fall back to DOM-scraped data.
            if not flights:
                flights = parse_dom_flights(
                    raw.get("dom_flights", []),
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date.isoformat(),
                    cabin_class=req.cabin_class,
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("ANA crawl failed for %s->%s", req.origin, req.destination)
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if ANA's website is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for Playwright-per-request model)."""
        await self._client.close()
