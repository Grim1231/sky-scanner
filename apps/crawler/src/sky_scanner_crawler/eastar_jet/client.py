"""HTTP client for Eastar Jet's kraken API (dotRez / Navitaire)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import httpx

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://kraken.eastarjet.com"
_ORIGIN = "https://main.eastarjet.com"


class EastarJetClient:
    """Async wrapper around Eastar Jet's ``kraken.eastarjet.com`` API.

    Eastar Jet uses dotRez (Navitaire by Amadeus) as its booking engine.
    All API calls require an anonymous session created via
    ``GET /passport/v1/session/create``.
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Origin": _ORIGIN,
                "Referer": f"{_ORIGIN}/",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            timeout=httpx.Timeout(timeout),
        )
        self._session_token: str | None = None
        self._jsession_id: str | None = None

    async def _ensure_session(self) -> None:
        """Create an anonymous dotRez session if not already established."""
        if self._session_token and self._jsession_id:
            return
        resp = await self._client.get("/passport/v1/session/create")
        resp.raise_for_status()
        data = resp.json()
        session_data = data.get("data", {})
        self._session_token = session_data["sessionXsessionId"]
        self._jsession_id = session_data["jsessionId"]
        logger.debug("Eastar Jet session created: JSESSIONID=%s", self._jsession_id)

    def _session_cookies(self) -> str:
        """Build cookie header string with session tokens."""
        token_encoded = quote(f"JTI={self._session_token}", safe="=")
        return f"JSESSIONID={self._jsession_id}; USER_STATE={token_encoded}"

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, KeyError),
    )
    async def search_daily_low_fares(
        self,
        origin: str,
        destination: str,
        begin_date: str,
        end_date: str,
        currency: str = "KRW",
    ) -> dict[str, Any]:
        """Fetch daily lowest fares for a route/date range.

        Parameters
        ----------
        origin:
            Station code (e.g. ``SEL``, ``ICN``, ``PUS``).
            ``SEL`` = Seoul metro area (covers both ICN + GMP).
        destination:
            Station code (e.g. ``NRT``, ``CJU``).
        begin_date:
            Start date as ``YYYY-MM-DD``.
        end_date:
            End date as ``YYYY-MM-DD``.
        currency:
            Currency code (default ``KRW``).

        Returns
        -------
        dict
            Raw JSON response from the API.
        """
        await self._ensure_session()
        resp = await self._client.post(
            "/availability/v1/dailyLowFare",
            headers={
                "Content-Type": "application/json",
                "Cookie": self._session_cookies(),
            },
            json={
                "beginDate": begin_date,
                "endDate": end_date,
                "originStationCodes": origin,
                "destinationStationCodes": destination,
                "currency": currency,
            },
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

        if data.get("errors"):
            msg = str(data["errors"])
            # Session expired — force re-create on next call
            if "SESSION_INVALID" in msg:
                self._session_token = None
                self._jsession_id = None
            raise RuntimeError(f"Eastar Jet API error: {msg}")

        return data

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, KeyError),
    )
    async def get_departure_routes(self) -> list[dict[str, Any]]:
        """Fetch all departure stations in the route network."""
        await self._ensure_session()
        resp = await self._client.get(
            "/route/v1/route/departureRoute",
            headers={"Cookie": self._session_cookies()},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data.get("data", [])

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, KeyError),
    )
    async def get_arrival_routes(self, origin: str) -> list[dict[str, Any]]:
        """Fetch arrival stations reachable from a given departure station."""
        await self._ensure_session()
        resp = await self._client.get(
            f"/route/v1/route/arrivalRoute/{origin}",
            headers={"Cookie": self._session_cookies()},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data.get("data", [])

    async def health_check(self) -> bool:
        """Check if the Eastar Jet API is reachable."""
        try:
            await self._ensure_session()
            routes = await self.get_departure_routes()
            return len(routes) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the underlying HTTPX client."""
        await self._client.aclose()
