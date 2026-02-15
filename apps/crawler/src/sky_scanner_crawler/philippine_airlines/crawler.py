"""Philippine Airlines L2 crawler -- flight schedules via the PAL flight status API.

Uses the public flight status API on ``www.philippineairlines.com`` to retrieve
scheduled flights for a given route and date.  No authentication required.

Limitations:
- **No fare/pricing data** -- schedule only (flight numbers, times, airports).
- Date range limited to ~14 days into the future.
- Fare search requires the Amadeus DES API (``api-des.philippineairlines.com``)
  which is protected by Imperva bot detection (``X-D-Token`` header) and is
  therefore not viable for L2 HTTP crawling.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import PhilippineAirlinesClient
from .response_parser import parse_flight_status

logger = logging.getLogger(__name__)


class PhilippineAirlinesCrawler(BaseCrawler):
    """L2 crawler: Philippine Airlines flight schedules via flight status API.

    Returns flights with schedule data (departure/arrival times,
    flight numbers, airports) but **no pricing information**.
    Only covers the next ~14 days of schedule data.
    """

    def __init__(self) -> None:
        self._client = PhilippineAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flight schedule for the requested route and date."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_flights_by_route(
                origin=req.origin,
                destination=req.destination,
                flight_date=req.departure_date,
            )

            flights = parse_flight_status(
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
            logger.exception("Philippine Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Philippine Airlines flight status API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
