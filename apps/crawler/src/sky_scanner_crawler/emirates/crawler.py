"""Emirates L2 crawler -- featured fares via the Emirates service API.

Covers Emirates (EK) by calling the public ``/service/featured-fares``
JSON endpoint that the emirates.com Next.js SPA uses.

The featured-fares API returns promotional fare cards with prices
for all Emirates routes from a given country/origin.  This provides
rich price signal data without authentication.

Uses ``primp`` with Chrome TLS impersonation for requests.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CrawlResult, CrawlTask, DataSource

from ..base import BaseCrawler
from ..config import settings
from .client import EmiratesClient
from .response_parser import parse_featured_fares

logger = logging.getLogger(__name__)

# Map country codes to Emirates locale strings.
_COUNTRY_LOCALE_MAP: dict[str, str] = {
    "KR": "en-kr",
    "US": "en-us",
    "GB": "en-gb",
    "AE": "en-ae",
    "JP": "en-jp",
    "SG": "en-sg",
    "AU": "en-au",
    "IN": "en-in",
    "DE": "en-de",
    "FR": "en-fr",
}


def _get_country_for_origin(origin: str) -> str:
    """Infer the country code from the origin airport.

    Uses common airport-to-country mappings for Emirates hubs
    and major departure points.
    """
    airport_country: dict[str, str] = {
        "ICN": "KR",
        "GMP": "KR",
        "JFK": "US",
        "LAX": "US",
        "SFO": "US",
        "ORD": "US",
        "LHR": "GB",
        "DXB": "AE",
        "NRT": "JP",
        "HND": "JP",
        "KIX": "JP",
        "SIN": "SG",
        "SYD": "AU",
        "MEL": "AU",
        "DEL": "IN",
        "BOM": "IN",
        "FRA": "DE",
        "CDG": "FR",
        "BKK": "TH",
        "HKG": "HK",
    }
    return airport_country.get(origin.upper(), "KR")


class EmiratesCrawler(BaseCrawler):
    """L2 crawler: Emirates featured fares via the service API.

    Fetches promotional fares from the ``/service/featured-fares``
    endpoint.  Returns one ``NormalizedFlight`` per fare card
    for the requested origin/destination, containing the promotional
    price with travel period metadata.
    """

    def __init__(self) -> None:
        self._client = EmiratesClient(timeout=settings.l2_timeout)

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Fetch Emirates featured fares for the requested route."""
        start = time.monotonic()
        req = task.search_request

        # Determine the country locale for the origin airport.
        country = _get_country_for_origin(req.origin)
        locale = _COUNTRY_LOCALE_MAP.get(country, "en-kr")

        try:
            raw = await self._client.get_featured_fares(
                country_language=locale,
                geocountrycode=country.lower(),
            )

            flights = parse_featured_fares(
                raw,
                origin_filter=req.origin,
                destination_filter=req.destination,
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
            logger.exception("Emirates crawl failed")
            return CrawlResult(
                source=DataSource.DIRECT_CRAWL,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Check if the Emirates service API is reachable."""
        return await self._client.health_check()

    async def close(self) -> None:
        """Release resources (no-op for primp per-request clients)."""
        await self._client.close()
