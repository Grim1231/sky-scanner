"""Air Seoul L2 crawler — fetches flight availability via primp TLS bypass."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import AirSeoulClient
from .response_parser import parse_flight_info

logger = logging.getLogger(__name__)


class AirSeoulCrawler(BaseCrawler):
    """L2 crawler: Air Seoul flight search via ``flyairseoul.com``.

    Uses ``primp`` with Chrome 131 TLS fingerprint impersonation to
    bypass Cloudflare protection.  Unlike the calendar-only Jeju Air
    and Eastar Jet crawlers, Air Seoul returns **individual flights**
    with actual departure/arrival times, flight numbers, and multiple
    fare tiers (PROMOTIONAL / DISCOUNT / NORMAL).

    Endpoint: ``POST /I/KO/searchFlightInfo.do`` (form-encoded).
    """

    def __init__(self) -> None:
        self._client = AirSeoulClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flights for the requested date."""
        start = time.monotonic()
        req = task.search_request

        departure_date = req.departure_date.strftime("%Y%m%d")

        try:
            raw = await self._client.search_flight_info(
                origin=req.origin,
                destination=req.destination,
                departure_date=departure_date,
                adults=req.passengers.adults if req.passengers else 1,
                children=req.passengers.children if req.passengers else 0,
                infants=(
                    req.passengers.infants_in_seat + req.passengers.infants_on_lap
                    if req.passengers
                    else 0
                ),
            )

            flights = parse_flight_info(
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
            logger.exception("Air Seoul crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Air Seoul API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the primp client."""
        await self._client.close()
