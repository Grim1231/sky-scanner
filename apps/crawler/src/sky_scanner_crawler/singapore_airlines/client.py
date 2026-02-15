"""Async HTTP client for the Singapore Airlines NDC Flight Availability API.

Singapore Airlines exposes a public NDC-style JSON API at
``developer.singaporeair.com``.  Authentication is via a static API key
passed in the ``apikey`` header.

Endpoint::

    POST / flightavailability / get

Returns per-recommendation data: flight legs, operating/marketing carriers,
durations, fare families, and per-passenger pricing with tax breakdown.

API portal: https://developer.singaporeair.com
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

import httpx

from sky_scanner_crawler.config import settings
from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

_BASE_URL = "https://developer.singaporeair.com"

# Map internal CabinClass values to SQ API cabin codes.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "Y",
    "PREMIUM_ECONOMY": "S",
    "BUSINESS": "J",
    "FIRST": "F",
}


class SingaporeAirlinesClient:
    """Async client for the Singapore Airlines NDC Flight Availability API."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    def _ensure_config(self) -> None:
        if not settings.singapore_api_key:
            raise RuntimeError(
                "CRAWLER_SINGAPORE_API_KEY must be set in environment or .env"
            )

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=_BASE_URL,
                timeout=httpx.Timeout(self._timeout, connect=10),
            )
        return self._http

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, RuntimeError),
    )
    async def get_flight_availability(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        cabin_class: str = "ECONOMY",
        adults: int = 1,
        children: int = 0,
        infants: int = 0,
        currency: str = "KRW",
    ) -> dict[str, Any]:
        """Search for available Singapore Airlines flights.

        Parameters
        ----------
        origin:
            3-letter IATA airport code (e.g. ``SIN``, ``ICN``).
        destination:
            3-letter IATA airport code (e.g. ``ICN``, ``NRT``).
        departure_date:
            Departure date.
        cabin_class:
            One of ``ECONOMY``, ``PREMIUM_ECONOMY``, ``BUSINESS``, ``FIRST``.
        adults:
            Number of adult passengers.
        children:
            Number of child passengers.
        infants:
            Number of infant passengers.
        currency:
            ISO currency code for pricing.

        Returns
        -------
        dict
            Raw API response JSON containing ``status``, ``response``
            with ``recommendations``, fare info, and flight details.
        """
        self._ensure_config()
        http = await self._ensure_http()

        sq_cabin = _CABIN_MAP.get(cabin_class, "Y")

        payload: dict[str, Any] = {
            "clientUUID": str(uuid.uuid4()),
            "request": {
                "itineraryDetails": [
                    {
                        "originAirportCode": origin.upper(),
                        "destinationAirportCode": destination.upper(),
                        "departureDate": departure_date.isoformat(),
                        "cabinClass": sq_cabin,
                        "adultCount": adults,
                        "childCount": children,
                        "infantCount": infants,
                    }
                ]
            },
        }

        headers = {
            "Content-Type": "application/json",
            "apikey": settings.singapore_api_key,
        }

        resp = await http.post(
            "/flightavailability/get",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        status = data.get("status", "")
        if status != "SUCCESS":
            code = data.get("code", "")
            message = data.get("message", "Unknown error")
            msg = f"SQ API error: {code} - {message}"
            raise RuntimeError(msg)

        # Log the number of recommendations found.
        recommendations = data.get("response", {}).get("recommendations", [])
        logger.debug(
            "SQ %s->%s (%s): %d recommendations",
            origin,
            destination,
            departure_date.isoformat(),
            len(recommendations),
        )
        return data

    async def health_check(self) -> bool:
        """Check if the Singapore Airlines API is reachable and key is valid.

        Performs a minimal flight search (SIN->KUL) to verify connectivity.
        """
        try:
            from datetime import date, timedelta

            test_date = date.today() + timedelta(days=30)
            data = await self.get_flight_availability(
                origin="SIN",
                destination="KUL",
                departure_date=test_date,
                cabin_class="ECONOMY",
                adults=1,
                currency="SGD",
            )
            return data.get("status") == "SUCCESS"
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None
