"""Vietnam Airlines L2 crawler -- flights via the VN middleware API.

Uses the public Vietnam Airlines middleware API at
``integration-middleware-website.vietnamairlines.com/api/v1``
to fetch flight schedules and fare data.

No API key or authentication is required.  The middleware sits
on a separate subdomain from the Imperva-protected booking site.

Strategy:
1. Call ``schedule-table`` for the route/date to get flight times,
   aircraft types, and operating carriers.
2. Call ``air-best-price`` for the same route/date to get the
   lowest fare per departure date.
3. Merge: attach per-date pricing to each schedule flight.

Limitations:
- Pricing is the *lowest* fare per day (no per-flight or per-cabin
  fare breakdown; all flights on the same date get the same price).
- The schedule endpoint returns flights across a ~7-day window;
  we filter to the exact requested date.
- Only VN-marketed flights are returned (VN, BL/Pacific Airlines
  codeshares).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import VietnamAirlinesClient
from .response_parser import (
    merge_schedule_with_prices,
    parse_best_prices,
    parse_flight_schedule,
)

logger = logging.getLogger(__name__)


class VietnamAirlinesCrawler(BaseCrawler):
    """L2 crawler: Vietnam Airlines flights via middleware API.

    Combines schedule data (flight times, aircraft, operators) with
    fare calendar data (lowest price per day) to produce priced
    flight results.
    """

    def __init__(self) -> None:
        self._client = VietnamAirlinesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch flights for the requested route and date."""
        start = time.monotonic()
        req = task.search_request
        target_date = req.departure_date.isoformat()

        try:
            # Fetch schedule and fares in parallel
            import asyncio

            schedule_task = asyncio.create_task(
                self._client.get_flight_schedule(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                )
            )
            fare_task = asyncio.create_task(
                self._client.get_best_prices(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                    range_of_departure=7,
                )
            )

            schedule_raw, fare_raw = await asyncio.gather(
                schedule_task, fare_task, return_exceptions=True
            )

            # Parse schedule (required)
            if isinstance(schedule_raw, BaseException):
                raise schedule_raw

            flights = parse_flight_schedule(
                schedule_raw,
                target_date=target_date,
                cabin_class=req.cabin_class,
            )

            # Parse fares (optional -- schedule alone is still useful)
            if isinstance(fare_raw, BaseException):
                logger.warning("VN fare fetch failed (schedule-only): %s", fare_raw)
            else:
                price_map = parse_best_prices(fare_raw)
                flights = merge_schedule_with_prices(
                    flights, price_map, target_date=target_date
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
            logger.exception("Vietnam Airlines crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Vietnam Airlines middleware is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release the HTTP client."""
        await self._client.close()
