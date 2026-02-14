"""Eastar Jet L2 crawler — fetches daily lowest fares via the kraken API."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import EastarJetClient
from .response_parser import parse_daily_low_fares

logger = logging.getLogger(__name__)


class EastarJetCrawler(BaseCrawler):
    """L2 crawler: Eastar Jet daily lowest-fare calendar API.

    Uses the ``kraken.eastarjet.com`` API (dotRez / Navitaire by Amadeus).
    Requires an anonymous session created via ``/passport/v1/session/create``.
    Returns one ``NormalizedFlight`` per day for a ~30-day window starting
    from the requested departure date, containing the lowest available fare.
    """

    def __init__(self) -> None:
        self._client = EastarJetClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch lowest fares for a 30-day window from the departure date."""
        start = time.monotonic()
        req = task.search_request

        begin_date = req.departure_date.isoformat()
        end_date = (req.departure_date + timedelta(days=30)).isoformat()

        try:
            raw = await self._client.search_daily_low_fares(
                origin=req.origin,
                destination=req.destination,
                begin_date=begin_date,
                end_date=end_date,
            )

            flights = parse_daily_low_fares(
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
            logger.exception("Eastar Jet crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Eastar Jet API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
