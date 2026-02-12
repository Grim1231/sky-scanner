"""Kiwi Tequila L2 crawler implementation."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sky_scanner_core.schemas import CabinClass, CrawlResult, CrawlTask, DataSource
from sky_scanner_crawler.base import BaseCrawler
from sky_scanner_crawler.config import settings

from .client import KiwiClient
from .response_parser import parse_kiwi_response

logger = logging.getLogger(__name__)

_CABIN_MAP: dict[CabinClass, str] = {
    CabinClass.ECONOMY: "M",
    CabinClass.PREMIUM_ECONOMY: "W",
    CabinClass.BUSINESS: "C",
    CabinClass.FIRST: "F",
}


class KiwiCrawler(BaseCrawler):
    """L2 crawler that fetches flight data from the Kiwi Tequila API."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._client = KiwiClient(
            api_key=api_key,
            timeout=settings.l2_timeout,
        )

    # ------------------------------------------------------------------
    # BaseCrawler interface
    # ------------------------------------------------------------------

    async def crawl(self, task: CrawlTask) -> CrawlResult:
        """Execute a search against Kiwi and return normalized results."""
        start = time.monotonic()
        req = task.search_request

        params: dict[str, object] = {
            "fly_from": req.origin,
            "fly_to": req.destination,
            "date_from": req.departure_date.strftime("%d/%m/%Y"),
            "date_to": req.departure_date.strftime("%d/%m/%Y"),
            "adults": req.passengers.adults,
            "children": req.passengers.children,
            "infants": (req.passengers.infants_in_seat + req.passengers.infants_on_lap),
            "selected_cabins": _CABIN_MAP.get(req.cabin_class, "M"),
            "curr": req.currency,
            "limit": 50,
        }

        if req.return_date is not None:
            params["return_from"] = req.return_date.strftime("%d/%m/%Y")
            params["return_to"] = req.return_date.strftime("%d/%m/%Y")

        try:
            raw = await self._client.search_flights(params)
            flights = parse_kiwi_response(raw, cabin_class=req.cabin_class)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CrawlResult(
                flights=flights,
                source=DataSource.KIWI_API,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Kiwi crawl failed: %s", exc)
            return CrawlResult(
                source=DataSource.KIWI_API,
                crawled_at=datetime.now(tz=UTC),
                duration_ms=elapsed_ms,
                error=str(exc),
                success=False,
            )

    async def health_check(self) -> bool:
        """Return *True* if the API key is configured and the API is reachable."""
        if not settings.kiwi_api_key:
            return False
        try:
            resp = await self._client.search_flights(
                {
                    "fly_from": "ICN",
                    "fly_to": "NRT",
                    "date_from": "01/01/2099",
                    "date_to": "01/01/2099",
                    "adults": 1,
                    "limit": 1,
                },
            )
            return "data" in resp
        except Exception:
            return False

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.close()
