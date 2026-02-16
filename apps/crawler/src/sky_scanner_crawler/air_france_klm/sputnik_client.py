"""HTTP client for Air France-KLM fare search via EveryMundo Sputnik API.

Air France (AF) and KLM (KL) both use EveryMundo's airTrfx platform to
publish lowest fares.  The ``airfare-sputnik-service`` exposes a fare search
endpoint that returns daily lowest one-way fares across the entire AF/KL
route network.

Flow:
1. POST ``openair-california.airtrfx.com/airfare-sputnik-service/
   v3/{tenant}/fares/search``
   with ``departureDaysInterval``, ``routesLimit``, ``faresLimit``, and
   optional ``origin`` / ``destination`` filters.
2. Authenticate via the ``em-api-key`` header (public key shared across
   EveryMundo airline tenants).
3. Include ``Referer`` and ``Origin`` headers pointing to the airline's page
   (required by Cloudflare / CORS policy).

This replaces the previous L3 Playwright client which could not bypass
Akamai's HTTP/2 TLS fingerprinting on klm.us / klm.com / airfrance.com
(all three domains return ``ERR_HTTP2_PROTOCOL_ERROR`` for both bundled
Chromium and system Chrome via Playwright).

The Sputnik API returns an array of fare objects, each containing:
- ``outboundFlight.departureAirportIataCode`` / ``arrivalAirportIataCode``
- ``priceSpecification.totalPrice`` / ``currencyCode``
- ``departureDate`` (YYYY-MM-DD)
- ``outboundFlight.fareClass`` (ECONOMY, BUSINESS, etc.)
- ``flightType`` (DOMESTIC / INTERNATIONAL)

Note: the ``origin`` and ``destination`` body parameters influence ranking but
the API still returns fares across all routes sorted by price.  Filtering
to the requested route must happen client-side.

Additionally, the ``hangar-service`` airport search endpoint provides the full
list of AF/KL destinations with IATA codes, useful for building route pairs
programmatically.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

# Sputnik fare search URLs per tenant.
_AF_FARE_SEARCH_URL = (
    "https://openair-california.airtrfx.com/airfare-sputnik-service/v3/af/fares/search"
)
_KL_FARE_SEARCH_URL = (
    "https://openair-california.airtrfx.com/airfare-sputnik-service/v3/kl/fares/search"
)

# Airport search (hangar-service) URLs per tenant.
_AF_AIRPORT_SEARCH_URL = (
    "https://openair-california.airtrfx.com/hangar-service/v2/af/airports/search"
)
_KL_AIRPORT_SEARCH_URL = (
    "https://openair-california.airtrfx.com/hangar-service/v2/kl/airports/search"
)

# Referer / Origin per tenant (CORS requirement).
_TENANT_CONFIG: dict[str, dict[str, str]] = {
    "AF": {
        "fare_url": _AF_FARE_SEARCH_URL,
        "airport_url": _AF_AIRPORT_SEARCH_URL,
        "referer": "https://www.airfrance.com/",
        "origin": "https://www.airfrance.com",
    },
    "KL": {
        "fare_url": _KL_FARE_SEARCH_URL,
        "airport_url": _KL_AIRPORT_SEARCH_URL,
        "referer": "https://www.klm.com/",
        "origin": "https://www.klm.com",
    },
}

# Public EM API key shared across EveryMundo airline tenants.
_EM_API_KEY = "HeQpRjsFI5xlAaSx2onkjc1HTK0ukqA1IrVvd5fvaMhNtzLTxInTpeYB1MK93pah"

# Default search parameters.
_DEFAULT_DAYS_INTERVAL_MIN = 1
_DEFAULT_DAYS_INTERVAL_MAX = 300
_DEFAULT_ROUTES_LIMIT = 100
_DEFAULT_FARES_LIMIT = 500
_DEFAULT_FARES_PER_ROUTE = 5
_DEFAULT_CURRENCY = "KRW"

# Airline names for external reference.
AIRLINE_NAMES: dict[str, str] = {
    "AF": "Air France",
    "KL": "KLM Royal Dutch Airlines",
}

# Airline codes served by this client.
AFKLM_AIRLINES = frozenset({"AF", "KL"})


class AirFranceKlmSputnikClient:
    """Async client for Air France-KLM fare search via EveryMundo Sputnik.

    Provides ``search_fares()`` for both AF and KL tenants via the shared
    Sputnik API.  Each call creates a fresh ``primp`` HTTP client with
    Chrome TLS impersonation.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    def _fetch_fares(
        self,
        tenant: str,
        origin: str | None,
        destination: str | None,
        *,
        currency: str = _DEFAULT_CURRENCY,
        days_min: int = _DEFAULT_DAYS_INTERVAL_MIN,
        days_max: int = _DEFAULT_DAYS_INTERVAL_MAX,
        routes_limit: int = _DEFAULT_ROUTES_LIMIT,
        fares_limit: int = _DEFAULT_FARES_LIMIT,
        fares_per_route: int = _DEFAULT_FARES_PER_ROUTE,
    ) -> list[dict[str, Any]]:
        """Synchronous fare fetch (runs via ``asyncio.to_thread``)."""
        tenant_upper = tenant.upper()
        cfg = _TENANT_CONFIG.get(tenant_upper)
        if cfg is None:
            msg = f"Unknown AF-KLM tenant: {tenant}"
            raise ValueError(msg)

        client = self._new_client()

        body: dict[str, Any] = {
            "currency": currency,
            "departureDaysInterval": {"min": days_min, "max": days_max},
            "routesLimit": routes_limit,
            "faresLimit": fares_limit,
            "faresPerRoute": fares_per_route,
        }
        if origin:
            body["origin"] = origin
        if destination:
            body["destination"] = destination

        headers = {
            "em-api-key": _EM_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": cfg["referer"],
            "Origin": cfg["origin"],
        }

        resp = client.post(cfg["fare_url"], headers=headers, json=body)

        if resp.status_code != 200:
            msg = f"{tenant_upper} fare search: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    def _fetch_airports(
        self,
        tenant: str,
        *,
        airport_type: str = "ORIGIN",
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Synchronous airport fetch (runs via ``asyncio.to_thread``)."""
        tenant_upper = tenant.upper()
        cfg = _TENANT_CONFIG.get(tenant_upper)
        if cfg is None:
            msg = f"Unknown AF-KLM tenant: {tenant}"
            raise ValueError(msg)

        client = self._new_client()

        body: dict[str, Any] = {
            "outputFields": [
                "locationLabel",
                "name",
                "countryName",
                "iataCode",
                "countryIsoCode",
            ],
            "setting": {"airportSource": "LAMBDA", "routeSource": "LAMBDA"},
            "sortingDetails": [{"field": "name", "order": "ASC"}],
            "from": 0,
            "size": 6000,
            "language": language,
            "routeOption": {"airportType": airport_type},
        }

        headers = {
            "em-api-key": _EM_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": cfg["referer"],
            "Origin": cfg["origin"],
        }

        resp = client.post(cfg["airport_url"], headers=headers, json=body)

        if resp.status_code != 200:
            msg = f"{tenant_upper} airport search: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_fares(
        self,
        tenant: str = "AF",
        origin: str | None = None,
        destination: str | None = None,
        *,
        currency: str = _DEFAULT_CURRENCY,
        days_min: int = _DEFAULT_DAYS_INTERVAL_MIN,
        days_max: int = _DEFAULT_DAYS_INTERVAL_MAX,
        routes_limit: int = _DEFAULT_ROUTES_LIMIT,
        fares_limit: int = _DEFAULT_FARES_LIMIT,
        fares_per_route: int = _DEFAULT_FARES_PER_ROUTE,
    ) -> list[dict[str, Any]]:
        """Fetch daily lowest fares for Air France or KLM routes.

        Parameters
        ----------
        tenant:
            ``"AF"`` for Air France or ``"KL"`` for KLM.
        origin:
            IATA airport code to filter origin (e.g. ``ICN``).
            If ``None``, fares from all origins are returned.
        destination:
            IATA airport code to filter destination (e.g. ``CDG``).
            If ``None``, fares to all destinations are returned.
        currency:
            ISO currency code (default ``KRW``).
        days_min:
            Minimum days from today for departure window.
        days_max:
            Maximum days from today for departure window.
        routes_limit:
            Max number of routes to return (default 100).
        fares_limit:
            Max total fare entries to return (default 500).
        fares_per_route:
            Max fares per individual route (default 5).

        Returns
        -------
        list[dict]
            Raw fare entries from the Sputnik API.
        """
        result = await asyncio.to_thread(
            self._fetch_fares,
            tenant,
            origin,
            destination,
            currency=currency,
            days_min=days_min,
            days_max=days_max,
            routes_limit=routes_limit,
            fares_limit=fares_limit,
            fares_per_route=fares_per_route,
        )
        priced = sum(
            1
            for e in result
            if e.get("priceSpecification", {}).get("totalPrice", 0) > 0
        )
        logger.debug(
            "%s fares %s->%s: %d entries, %d with prices",
            tenant.upper(),
            origin or "*",
            destination or "*",
            len(result),
            priced,
        )
        return result

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_airports(
        self,
        tenant: str = "AF",
        *,
        airport_type: str = "ORIGIN",
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Fetch all AF or KL airports/destinations.

        Parameters
        ----------
        tenant:
            ``"AF"`` for Air France or ``"KL"`` for KLM.
        airport_type:
            ``"ORIGIN"`` for departure airports or ``"DESTINATION"`` for
            arrival airports.
        language:
            Language code for airport labels (default ``"en"``).

        Returns
        -------
        list[dict]
            Airport entries with ``iataCode``, ``name``, and ``country`` info.
        """
        result = await asyncio.to_thread(
            self._fetch_airports,
            tenant,
            airport_type=airport_type,
            language=language,
        )
        logger.debug(
            "%s %s airports: %d entries",
            tenant.upper(),
            airport_type,
            len(result),
        )
        return result

    async def health_check(self) -> bool:
        """Check if the AF-KLM Sputnik fare API is accessible."""
        try:
            # Test AF first (larger network), fall back to KL.
            data = await self.search_fares(
                tenant="AF",
                origin="CDG",
                routes_limit=5,
                fares_limit=10,
                fares_per_route=2,
            )
            return any(
                e.get("priceSpecification", {}).get("totalPrice", 0) > 0 for e in data
            )
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
