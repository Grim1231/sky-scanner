"""Amadeus Self-Service API client wrapper.

Uses the official ``amadeus`` Python SDK which handles OAuth2 token
lifecycle automatically.  Exposes a thin async wrapper around the
synchronous SDK using ``asyncio.to_thread``.
"""

from __future__ import annotations

import logging
from typing import Any

from amadeus import Client, ResponseError

from sky_scanner_crawler.config import settings

logger = logging.getLogger(__name__)


class AmadeusClient:
    """Async-friendly wrapper around the Amadeus Python SDK."""

    def __init__(self) -> None:
        self._sdk: Client | None = None

    def _ensure_sdk(self) -> Client:
        if self._sdk is None:
            if not settings.amadeus_client_id or not settings.amadeus_client_secret:
                raise RuntimeError(
                    "CRAWLER_AMADEUS_CLIENT_ID and CRAWLER_AMADEUS_CLIENT_SECRET "
                    "must be set in environment or .env"
                )
            self._sdk = Client(
                client_id=settings.amadeus_client_id,
                client_secret=settings.amadeus_client_secret,
                hostname=settings.amadeus_hostname,
            )
            logger.info(
                "Amadeus SDK initialised (hostname=%s)", settings.amadeus_hostname
            )
        return self._sdk

    async def search_flight_offers(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        *,
        return_date: str | None = None,
        adults: int = 1,
        travel_class: str | None = None,
        non_stop: bool = False,
        currency_code: str = "KRW",
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search for flight offers using GET /v2/shopping/flight-offers.

        Parameters
        ----------
        origin:
            IATA origin code (e.g. ``ICN``).
        destination:
            IATA destination code (e.g. ``SIN``).
        departure_date:
            ISO-8601 date string (``YYYY-MM-DD``).
        return_date:
            Optional return date for round-trip searches.
        adults:
            Number of adult passengers (1-9).
        travel_class:
            ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST.
        non_stop:
            If True, return only non-stop flights.
        currency_code:
            ISO currency code for prices.
        max_results:
            Maximum number of offers to return (up to 250).
        """
        import asyncio

        sdk = self._ensure_sdk()
        params: dict[str, Any] = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "currencyCode": currency_code,
            "max": max_results,
        }
        if return_date:
            params["returnDate"] = return_date
        if travel_class:
            params["travelClass"] = travel_class
        if non_stop:
            params["nonStop"] = "true"

        def _call() -> list[dict[str, Any]]:
            try:
                resp = sdk.shopping.flight_offers_search.get(**params)
                return resp.data  # type: ignore[no-any-return]
            except ResponseError as exc:
                logger.error("Amadeus flight search failed: %s", exc)
                raise

        return await asyncio.to_thread(_call)

    async def get_airline_info(self, airline_code: str) -> dict[str, Any] | None:
        """Look up airline name by IATA code."""
        import asyncio

        sdk = self._ensure_sdk()

        def _call() -> dict[str, Any] | None:
            try:
                resp = sdk.reference_data.airlines.get(airlineCodes=airline_code)
                data: list[dict[str, Any]] = resp.data  # type: ignore[assignment]
                return data[0] if data else None
            except ResponseError:
                return None

        return await asyncio.to_thread(_call)

    async def health_check(self) -> bool:
        """Verify Amadeus API credentials are valid."""
        import asyncio

        try:
            sdk = self._ensure_sdk()

            def _call() -> bool:
                try:
                    resp = sdk.reference_data.airlines.get(airlineCodes="SQ")
                    return bool(resp.data)
                except ResponseError:
                    return False

            return await asyncio.to_thread(_call)
        except RuntimeError:
            return False

    async def close(self) -> None:
        """No-op — the SDK manages its own HTTP lifecycle."""
        self._sdk = None
