"""Turkish Airlines L2 crawler — flight availability via the TK website API.

Covers TK (Turkish Airlines) by calling the same internal JSON API
that the turkishairlines.com Next.js SPA uses.

Target endpoints (reverse-engineered):
    POST /api/v1/availability/flight-matrix — full search results
    POST /api/v1/availability/cheapest-prices — fare calendar (fallback)

The site uses Akamai Bot Manager which may intermittently block POST
requests.  GET endpoints (locations, parameters) are not protected.
Retries with fresh sessions are used to work around transient blocks.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import TurkishAirlinesClient
from .response_parser import parse_cheapest_prices, parse_flight_matrix

logger = logging.getLogger(__name__)


class TurkishAirlinesCrawler(BaseCrawler):
    """L2 crawler: Turkish Airlines flight search via website API.

    Attempts the ``flight-matrix`` endpoint first (full flight details
    with fares).  Falls back to ``cheapest-prices`` if the matrix
    returns no results.
    """

    def __init__(self) -> None:
        self._client = TurkishAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch TK flight availability for the requested route/date."""
        start = time.monotonic()
        req = task.search_request

        try:
            # Try flight-matrix first (includes full flight details).
            raw_matrix = await self._client.get_flight_matrix(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
            )

            flights = parse_flight_matrix(
                raw_matrix,
                cabin_class=req.cabin_class,
            )

            # Fallback to cheapest-prices if matrix returned no flights.
            if not flights:
                raw_prices = await self._client.get_cheapest_prices(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                    cabin_class=req.cabin_class.value,
                )
                flights = parse_cheapest_prices(
                    raw_prices,
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
            logger.exception("Turkish Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the TK website API is reachable.

        Uses the GET ``/api/v1/parameters`` endpoint which does not
        require Akamai sensor data.
        """
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for primp per-request clients)."""
        await self._client.close()
