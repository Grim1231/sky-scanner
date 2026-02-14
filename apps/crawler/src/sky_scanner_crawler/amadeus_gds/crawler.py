"""Amadeus GDS L2 crawler — flight offers via Amadeus Self-Service API."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from .client import AmadeusClient
from .response_parser import parse_flight_offers

logger = logging.getLogger(__name__)

# Map our CabinClass enum values to Amadeus travelClass parameter
_AMADEUS_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "ECONOMY",
    "PREMIUM_ECONOMY": "PREMIUM_ECONOMY",
    "BUSINESS": "BUSINESS",
    "FIRST": "FIRST",
}


class AmadeusCrawler(BaseCrawler):
    """L2 crawler: Amadeus GDS flight offers search.

    Uses the Amadeus Self-Service ``Flight Offers Search`` API to retrieve
    real-time fares from ~400 airlines.  Requires ``CRAWLER_AMADEUS_CLIENT_ID``
    and ``CRAWLER_AMADEUS_CLIENT_SECRET`` environment variables.
    """

    def __init__(self) -> None:
        self._client = AmadeusClient()

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Search for flights via the Amadeus GDS API."""
        start = time.monotonic()
        req = task.search_request

        travel_class = _AMADEUS_CABIN_MAP.get(req.cabin_class.value)

        try:
            raw_offers = await self._client.search_flight_offers(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date.isoformat(),
                adults=1,
                travel_class=travel_class,
                currency_code="KRW",
                max_results=50,
            )

            flights = parse_flight_offers(
                raw_offers,
                cabin_class=req.cabin_class,
            )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.GDS,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Amadeus GDS crawl failed")
            return CrawlResult(
                source=DataSource.GDS,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Amadeus API is reachable and credentials are valid."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the Amadeus client."""
        await self._client.close()
