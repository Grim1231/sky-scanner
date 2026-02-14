"""Jeju Air L2 crawler — fetches daily lowest fares via the booking calendar API."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import JejuAirClient
from .response_parser import parse_lowest_fares

logger = logging.getLogger(__name__)


class JejuAirCrawler(BaseCrawler):
    """L2 crawler: Jeju Air lowest-fare calendar API.

    Uses the publicly accessible ``sec.jejuair.net`` lowest-fare calendar
    endpoint (no authentication required).  Returns one ``NormalizedFlight``
    per day for the requested departure month, containing the lowest
    available fare including taxes.
    """

    def __init__(self) -> None:
        self._client = JejuAirClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch lowest fares for the month containing the departure date."""
        start = time.monotonic()
        req = task.search_request

        # Round to first of the month for the calendar API
        search_month = req.departure_date.replace(day=1).isoformat()

        try:
            raw = await self._client.search_lowest_fares(
                origin=req.origin,
                destination=req.destination,
                search_month=search_month,
                pax_count=req.passengers.adults if req.passengers else 1,
            )

            flights = parse_lowest_fares(
                raw,
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
            logger.exception("Jeju Air crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Jeju Air booking API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
