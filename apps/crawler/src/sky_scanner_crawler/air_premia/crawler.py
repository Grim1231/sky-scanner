"""Air Premia L3 crawler — Playwright-assisted low-fare API access."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import AirPremiaClient
from .response_parser import parse_low_fares

logger = logging.getLogger(__name__)


class AirPremiaCrawler(BaseCrawler):
    """L3 crawler: Air Premia daily lowest-fare calendar API.

    Uses Playwright to bypass Cloudflare JS Challenge on fare endpoints,
    then calls ``/api/v1/low-fares`` with extracted cookies.  Returns one
    ``NormalizedFlight`` per day for a ~30-day window.
    """

    def __init__(self) -> None:
        self._client = AirPremiaClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch lowest fares for a 30-day window from the departure date."""
        start = time.monotonic()
        req = task.search_request

        begin_date = req.departure_date.isoformat()
        end_date = (req.departure_date + timedelta(days=30)).isoformat()

        try:
            raw = await self._client.get_low_fares(
                origin=req.origin,
                destination=req.destination,
                begin_date=begin_date,
                end_date=end_date,
            )

            flights = parse_low_fares(
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
            logger.exception("Air Premia crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Air Premia API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
