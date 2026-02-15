"""Thai Airways (TG) L3 crawler -- Playwright search with response interception.

Navigates to the Thai Airways booking page, fills the search form, and
intercepts XHR/fetch responses from the Amadeus OSCI backend to extract
flight availability and pricing data.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import ThaiAirwaysClient
from .response_parser import parse_intercepted_responses

logger = logging.getLogger(__name__)


class ThaiAirwaysCrawler(BaseCrawler):
    """L3 crawler: Thai Airways flight search via Playwright.

    Uses Playwright to navigate the TG booking SPA, intercepts API
    responses from the Amadeus OSCI backend, and parses them into
    ``NormalizedFlight`` objects.
    """

    def __init__(self) -> None:
        self._client = ThaiAirwaysClient(timeout=30)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Search flights on thaiairways.com and return normalised results."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw_responses = await self._client.search_flights(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )

            flights = parse_intercepted_responses(
                raw_responses,
                origin=req.origin,
                destination=req.destination,
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
            logger.exception("Thai Airways crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Thai Airways website is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for Playwright-per-request)."""
        await self._client.close()
