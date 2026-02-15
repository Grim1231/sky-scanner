"""Cathay Pacific L2 crawler -- flight timetable and fare calendar via website APIs.

Covers CX (Cathay Pacific Airways) by calling the same internal JSON APIs
that the cathaypacific.com SPA uses.

Target endpoints (reverse-engineered):
    GET  api.cathaypacific.com/flightinformation/flightschedule/v2/flightTimetable
        -- flight schedule with segment details
    POST book.cathaypacific.com/CathayPacificV3/dyn/air/api/instant/histogram
        -- fare calendar (fallback for daily lowest prices)

The site uses Akamai Bot Manager.  ``primp`` with Chrome TLS
impersonation + cookie warm-up is used to bypass basic bot detection.
Retries with fresh sessions handle transient Akamai blocks.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import CathayPacificClient
from .response_parser import parse_histogram, parse_timetable

logger = logging.getLogger(__name__)


class CathayPacificCrawler(BaseCrawler):
    """L2 crawler: Cathay Pacific flight search via website APIs.

    Attempts the ``flightTimetable`` endpoint first (full flight schedule
    with segment details).  Falls back to the ``histogram`` endpoint if
    the timetable returns no results or fails (provides daily lowest
    prices without flight-level detail).
    """

    def __init__(self) -> None:
        self._client = CathayPacificClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch CX flight availability for the requested route/date."""
        start = time.monotonic()
        req = task.search_request

        try:
            flights = []

            # Try timetable first (full flight details).
            try:
                raw_timetable = await self._client.search_timetable(
                    origin=req.origin,
                    destination=req.destination,
                    departure_date=req.departure_date,
                    cabin_class=req.cabin_class.value,
                )

                flights = parse_timetable(
                    raw_timetable,
                    origin=req.origin,
                    destination=req.destination,
                    cabin_class=req.cabin_class,
                )
            except Exception:
                logger.warning(
                    "CX timetable failed for %s->%s, trying histogram",
                    req.origin,
                    req.destination,
                    exc_info=True,
                )

            # Fallback to histogram if timetable returned no flights.
            if not flights:
                try:
                    raw_histogram = await self._client.search_histogram(
                        origin=req.origin,
                        destination=req.destination,
                        departure_date=req.departure_date,
                        cabin_class=req.cabin_class.value,
                    )
                    flights = parse_histogram(
                        raw_histogram,
                        origin=req.origin,
                        destination=req.destination,
                        cabin_class=req.cabin_class,
                    )
                except Exception:
                    logger.warning(
                        "CX histogram also failed for %s->%s",
                        req.origin,
                        req.destination,
                        exc_info=True,
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
            logger.exception("Cathay Pacific crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Cathay Pacific API is reachable.

        Uses the IBE origin-destination endpoint which has lower
        protection than the timetable/search endpoints.
        """
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for primp per-request clients)."""
        await self._client.close()
