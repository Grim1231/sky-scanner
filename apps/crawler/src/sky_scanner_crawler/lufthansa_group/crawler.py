"""Lufthansa Group L2 crawler — flight schedules via the Lufthansa Open API.

Covers LH (Lufthansa), LX (Swiss), OS (Austrian), 4U (Eurowings),
SN (Brussels Airlines), EN (Air Dolomiti), WK (Edelweiss), and
4Y (Eurowings Discover).

Requires ``CRAWLER_LUFTHANSA_CLIENT_ID`` and ``CRAWLER_LUFTHANSA_CLIENT_SECRET``
environment variables obtained from https://developer.lufthansa.com.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import LufthansaClient
from .response_parser import parse_flight_schedules

logger = logging.getLogger(__name__)


class LufthansaCrawler(BaseCrawler):
    """L2 crawler: Lufthansa Group flight schedules via Open API."""

    def __init__(self) -> None:
        self._client = LufthansaClient()

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch Lufthansa Group schedules for the requested route/date."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw_schedules = await self._client.get_flight_schedules(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
            )

            flights = parse_flight_schedules(
                raw_schedules,
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
            logger.exception("Lufthansa Group crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Lufthansa API is reachable and credentials are valid."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
