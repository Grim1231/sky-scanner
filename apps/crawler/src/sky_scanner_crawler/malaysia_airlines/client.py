"""HTTP client for Malaysia Airlines low-fare calendar API.

Malaysia Airlines' website is built on Adobe Experience Manager (AEM) with a
Vue.js SPA frontend.  The booking widget's date-picker populates daily lowest
fares from an internal AEM Sling servlet exposed at::

    GET / bin / mh / revamp / lowFares

Parameters
----------
origin : str
    IATA code of the departure airport (e.g. ``KUL``).
destination : str
    IATA code of the arrival airport (e.g. ``SIN``).
firstdate : str   (one-way mode)
    Start date in ``DDMMYY`` format.  When present, the endpoint returns
    ~30 days of one-way fares from this date.
departdate : str  (return mode)
    Departure date in ``DDMMYY`` format.  When present together with
    ``fromDepartDate=true``, the response contains the outbound fare for
    that date **plus** a ``returnDetail`` array with return-leg daily fares
    for ~30 days.
paymentType : str
    ``Cash`` (revenue fares) or ``Miles`` (Enrich points redemption).

Response (one-way)::

    [
        {
            "refNo": "1",
            "dateOfDeparture": "150226",
            "totalFareAmount": "249.00",
            "totalTaxAmount": "112.00",
            "currency": "MYR",
            "isLowFare": false,
        },
        ...,
    ]

Response (return -- ``departdate`` + ``fromDepartDate=true``)::

    [
        {
            "dateOfDeparture": "150326",
            "totalFareAmount": "3390.00",
            "totalTaxAmount": "387.00",
            "currency": "MYR",
            "returnDetail": [
                {
                    "dateOfDeparture": "150326",
                    "totalFareAmount": "2325.00",
                    "totalTaxAmount": "369.00",
                    "currency": "MYR",
                },
                ...,
            ],
        }
    ]

The endpoint does **not** require authentication, session cookies, or API
keys.  A simple ``Referer`` header pointing to the MH homepage is included
for politeness, and ``primp`` provides TLS fingerprinting in case Cloudflare
ever tightens bot detection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.malaysiaairlines.com"
_LOW_FARE_PATH = "/bin/mh/revamp/lowFares"
_OND_LIST_PATH = "/bin/mh/revamp/ondLists"
_REFERER = "https://www.malaysiaairlines.com/my/en/home.html"


class MalaysiaAirlinesClient:
    """Async client for the Malaysia Airlines low-fare calendar API."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # One-way fares
    # ------------------------------------------------------------------

    def _fetch_oneway_fares(
        self,
        origin: str,
        destination: str,
        first_date: str,
        *,
        currency: str = "MYR",
    ) -> list[dict[str, Any]]:
        """Synchronous one-way fare fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()

        params = {
            "origin": origin,
            "destination": destination,
            "firstdate": first_date,
            "paymentType": "Cash",
        }

        headers = {
            "Accept": "application/json",
            "Referer": _REFERER,
        }

        resp = client.get(
            f"{_BASE_URL}{_LOW_FARE_PATH}",
            headers=headers,
            params=params,
        )

        if resp.status_code != 200:
            msg = f"MH lowFares one-way: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    # ------------------------------------------------------------------
    # Return fares (outbound + return-leg daily prices)
    # ------------------------------------------------------------------

    def _fetch_return_fares(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        *,
        currency: str = "MYR",
    ) -> list[dict[str, Any]]:
        """Synchronous return-fare fetch (runs via ``asyncio.to_thread``)."""
        client = self._new_client()

        params = {
            "origin": origin,
            "destination": destination,
            "departdate": depart_date,
            "fromDepartDate": "true",
            "paymentType": "Cash",
        }

        headers = {
            "Accept": "application/json",
            "Referer": _REFERER,
        }

        resp = client.get(
            f"{_BASE_URL}{_LOW_FARE_PATH}",
            headers=headers,
            params=params,
        )

        if resp.status_code != 200:
            msg = f"MH lowFares return: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: list[dict[str, Any]] = resp.json()
        return data

    # ------------------------------------------------------------------
    # OND (Origin-Destination) route list
    # ------------------------------------------------------------------

    def _fetch_ond_list(self, list_type: str = "base") -> dict[str, Any]:
        """Fetch the origin-destination list (synchronous)."""
        client = self._new_client()

        headers = {
            "Accept": "application/json",
            "Referer": _REFERER,
        }

        resp = client.get(
            f"{_BASE_URL}{_OND_LIST_PATH}",
            headers=headers,
            params={"type": list_type},
        )

        if resp.status_code != 200:
            msg = f"MH ondLists: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        data: dict[str, Any] = resp.json()
        return data

    # ------------------------------------------------------------------
    # Async public interface
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_oneway_fares(
        self,
        origin: str,
        destination: str,
        first_date: str,
        *,
        currency: str = "MYR",
    ) -> list[dict[str, Any]]:
        """Fetch ~30 days of one-way daily lowest fares.

        Parameters
        ----------
        origin:
            IATA departure airport code (e.g. ``KUL``).
        destination:
            IATA arrival airport code (e.g. ``SIN``).
        first_date:
            Start date in ``DDMMYY`` format (e.g. ``150326`` for 2026-03-15).
        currency:
            ISO currency code (default ``MYR``).

        Returns
        -------
        list[dict]
            Raw fare entries from the low-fare calendar endpoint.
        """
        result = await asyncio.to_thread(
            self._fetch_oneway_fares,
            origin,
            destination,
            first_date,
            currency=currency,
        )
        logger.debug(
            "MH one-way fares %s->%s from %s: %d entries",
            origin,
            destination,
            first_date,
            len(result),
        )
        return result

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(RuntimeError, OSError),
    )
    async def search_return_fares(
        self,
        origin: str,
        destination: str,
        depart_date: str,
        *,
        currency: str = "MYR",
    ) -> list[dict[str, Any]]:
        """Fetch return-trip daily fares for a given departure date.

        The response includes the outbound fare for ``depart_date`` and a
        ``returnDetail`` array with ~30 days of return-leg daily prices.

        Parameters
        ----------
        origin:
            IATA departure airport code.
        destination:
            IATA arrival airport code.
        depart_date:
            Departure date in ``DDMMYY`` format.
        currency:
            ISO currency code (default ``MYR``).

        Returns
        -------
        list[dict]
            Raw fare entries (usually a single-element list with nested
            ``returnDetail``).
        """
        result = await asyncio.to_thread(
            self._fetch_return_fares,
            origin,
            destination,
            depart_date,
            currency=currency,
        )
        logger.debug(
            "MH return fares %s->%s depart %s: %d entries",
            origin,
            destination,
            depart_date,
            len(result),
        )
        return result

    @async_retry(
        max_retries=2,
        base_delay=2.0,
        max_delay=15.0,
        exceptions=(RuntimeError, OSError),
    )
    async def fetch_ond_list(self, list_type: str = "base") -> dict[str, Any]:
        """Fetch the list of origin-destination pairs.

        Parameters
        ----------
        list_type:
            ``base`` for the full list, ``bst`` for the Business Suite /
            Travel list (smaller subset).

        Returns
        -------
        dict
            ``{"originList": [...], "destinationList": [...]}``
        """
        return await asyncio.to_thread(self._fetch_ond_list, list_type)

    async def health_check(self) -> bool:
        """Check if the MH low-fare API is accessible."""
        try:
            data = await self.search_oneway_fares("KUL", "SIN", "150326")
            return len(data) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
