"""Malaysia Airlines L2 crawler -- daily lowest fares via AEM low-fare calendar API.

Malaysia Airlines exposes an unauthenticated low-fare calendar endpoint at
``/bin/mh/revamp/lowFares`` (an AEM Sling servlet) that powers the fare
date-picker on their Vue.js booking widget.

The endpoint returns ~30 days of daily lowest fares for a given route in
either one-way or return mode.  Dates use ``DDMMYY`` format and prices are
in the market's local currency (default MYR).

**No API key, session cookie, or authentication is required.**

The crawler converts the departure date from the ``CrawlTask`` into ``DDMMYY``
format and requests fares starting from that date.  For round-trip tasks it
fetches the return-fare variant which also provides return-leg daily prices.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sky_scanner_core.schemas import CrawlResult, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import MalaysiaAirlinesClient
from .response_parser import parse_oneway_fares, parse_return_fares

if TYPE_CHECKING:
    from sky_scanner_core.schemas import CrawlTask

logger = logging.getLogger(__name__)


def _date_to_ddmmyy(dt: datetime | object) -> str:
    """Convert a ``date`` or ``datetime`` to ``DDMMYY`` string."""
    # CrawlTask.search_request.departure_date is a date object
    if hasattr(dt, "strftime"):
        return dt.strftime("%d%m%y")  # type: ignore[union-attr]
    return ""


class MalaysiaAirlinesCrawler(BaseCrawler):
    """L2 crawler: Malaysia Airlines daily lowest fares via AEM low-fare API.

    The low-fare calendar endpoint is a simple GET request that returns
    ~30 days of daily prices.  It does not require authentication.

    Two modes:

    * **One-way** (``firstdate``): flat list of daily fares.
    * **Return** (``departdate`` + ``fromDepartDate=true``): outbound fare
      plus a ``returnDetail`` array with return-leg daily fares.

    The ``CrawlTask.search_request.trip_type`` determines which mode is used.
    """

    def __init__(self) -> None:
        self._client = MalaysiaAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch daily lowest fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        try:
            date_str = _date_to_ddmmyy(req.departure_date)
            if not date_str:
                msg = "Invalid departure date"
                raise ValueError(msg)

            from sky_scanner_core.schemas import TripType

            if req.trip_type == TripType.ROUND_TRIP:
                raw = await self._client.search_return_fares(
                    origin=req.origin,
                    destination=req.destination,
                    depart_date=date_str,
                )
                flights = parse_return_fares(
                    raw,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )
            else:
                raw = await self._client.search_oneway_fares(
                    origin=req.origin,
                    destination=req.destination,
                    first_date=date_str,
                )
                flights = parse_oneway_fares(
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
            logger.exception("Malaysia Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the MH low-fare API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Shut down the HTTP client."""
        await self._client.close()
