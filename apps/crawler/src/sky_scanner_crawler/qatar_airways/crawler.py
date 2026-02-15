"""Qatar Airways (QR) L3 crawler -- Playwright search with qoreservices interception.

Navigates to the Qatar Airways booking page, fills the search form, and
intercepts JSON responses from ``qoreservices.qatarairways.com`` to extract
flight offers and pricing data.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import QatarAirwaysClient
from .response_parser import parse_intercepted_responses

logger = logging.getLogger(__name__)


class QatarAirwaysCrawler(BaseCrawler):
    """L3 crawler: Qatar Airways flight search via Playwright.

    Uses Playwright to navigate the QR Angular SPA booking page,
    intercepts API responses from ``qoreservices.qatarairways.com``,
    and parses them into ``NormalizedFlight`` objects.

    Falls back to the direct URL method if form-filling produces no
    intercepted responses.
    """

    def __init__(self) -> None:
        self._client = QatarAirwaysClient(timeout=30)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Search flights on qatarairways.com and return normalised results."""
        start = time.monotonic()
        req = task.search_request

        try:
            # Primary: form-filling approach.
            raw_responses = await self._client.search_flights(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )

            # Fallback: if no responses intercepted, try direct URL approach.
            if not raw_responses:
                logger.info("QR: form approach yielded no results; trying direct URL")
                raw_responses = await self._client.search_via_direct_url(
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
            logger.exception("Qatar Airways crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Qatar Airways website is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for Playwright-per-request)."""
        await self._client.close()
