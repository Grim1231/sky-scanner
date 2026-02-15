"""EVA Air L2 crawler -- daily lowest fares via getBestPrices API."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import EvaAirClient
from .response_parser import parse_best_prices

logger = logging.getLogger(__name__)


class EvaAirCrawler(BaseCrawler):
    """L2 crawler: EVA Air daily lowest fares via ``getBestPrices.ashx``.

    EVA Air publishes a fare calendar through their booking engine at
    ``booking.evaair.com``.  Requires a session cookie obtained by
    first visiting the main EVA Air homepage, then querying the
    ``getBestPrices.ashx`` handler with primp TLS fingerprinting.

    Returns up to ~300 days of daily lowest one-way fares for any
    route EVA operates.  Currency is auto-selected based on the
    departure city's country.
    """

    def __init__(self) -> None:
        self._client = EvaAirClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_best_prices(
                origin=req.origin,
                destination=req.destination,
            )

            flights = parse_best_prices(
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
            logger.exception("EVA Air crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the EVA Air fare API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self._client.close()
