"""Singapore Airlines L2 crawler -- flights via the SQ NDC API.

Uses the official Singapore Airlines developer API (developer.singaporeair.com)
to search for flight availability with pricing.

Requires ``CRAWLER_SINGAPORE_API_KEY`` environment variable, obtained by
registering an app at https://developer.singaporeair.com.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import SingaporeAirlinesClient
from .response_parser import parse_flight_availability

logger = logging.getLogger(__name__)


class SingaporeAirlinesCrawler(BaseCrawler):
    """L2 crawler: Singapore Airlines flight availability via NDC API.

    Returns flights with per-recommendation pricing including fare
    families, cabin classes, and tax breakdown.  Covers SQ-marketed
    and codeshare flights.
    """

    def __init__(self) -> None:
        self._client = SingaporeAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flight availability for the requested route and date."""
        start = time.monotonic()
        req = task.search_request

        try:
            raw = await self._client.get_flight_availability(
                origin=req.origin,
                destination=req.destination,
                departure_date=req.departure_date,
                cabin_class=req.cabin_class.value,
                adults=req.passengers.adults,
                children=req.passengers.children,
                infants=req.passengers.infants_on_lap,
                currency=req.currency,
            )

            flights = parse_flight_availability(
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
            logger.exception("Singapore Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Singapore Airlines API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
