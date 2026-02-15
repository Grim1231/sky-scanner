"""Lufthansa Group Open API client with OAuth2 token management.

Covers flight schedules for LH (Lufthansa), LX (Swiss), OS (Austrian),
4U (Eurowings), SN (Brussels Airlines), EN (Air Dolomiti), WK (Edelweiss),
and 4Y (Eurowings Discover).

API portal: https://developer.lufthansa.com
Auth: OAuth2 client_credentials grant
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from sky_scanner_crawler.config import settings
from sky_scanner_crawler.retry import async_retry

if TYPE_CHECKING:
    from datetime import date

logger = logging.getLogger(__name__)

# Lufthansa Group airline IATA codes served by this API.
LH_GROUP_AIRLINES = frozenset({"LH", "LX", "OS", "4U", "SN", "EN", "WK", "4Y"})

# Map of airline codes to full names.
AIRLINE_NAMES: dict[str, str] = {
    "LH": "Lufthansa",
    "LX": "Swiss International Air Lines",
    "OS": "Austrian Airlines",
    "4U": "Eurowings",
    "SN": "Brussels Airlines",
    "EN": "Air Dolomiti",
    "WK": "Edelweiss Air",
    "4Y": "Eurowings Discover",
}


class LufthansaClient:
    """Async HTTP client for the Lufthansa Open API with OAuth2 token caching.

    The OAuth2 token is obtained via ``POST /v1/oauth/token`` using the
    ``client_credentials`` grant.  Tokens are cached in-memory and refreshed
    automatically when they expire (or on 401 responses).
    """

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return f"https://{settings.lufthansa_hostname}"

    def _ensure_config(self) -> None:
        if not settings.lufthansa_client_id or not settings.lufthansa_client_secret:
            raise RuntimeError(
                "CRAWLER_LUFTHANSA_CLIENT_ID and "
                "CRAWLER_LUFTHANSA_CLIENT_SECRET must be set in environment "
                "or .env"
            )

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=self._base_url(),
                timeout=httpx.Timeout(settings.l2_timeout, connect=10),
            )
        return self._http

    # ------------------------------------------------------------------
    # OAuth2 token lifecycle
    # ------------------------------------------------------------------

    async def _fetch_token(self) -> None:
        """Obtain a fresh access token from the Lufthansa OAuth2 endpoint."""
        self._ensure_config()
        http = await self._ensure_http()
        resp = await http.post(
            "/v1/oauth/token",
            data={
                "client_id": settings.lufthansa_client_id,
                "client_secret": settings.lufthansa_client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        body = resp.json()
        self._access_token = body["access_token"]
        # Refresh 60 s before actual expiry to avoid edge-case 401s.
        expires_in: int = body.get("expires_in", 21600)
        self._token_expires_at = time.monotonic() + expires_in - 60
        logger.info("Lufthansa OAuth2 token acquired (expires_in=%ds)", expires_in)

    async def _ensure_token(self) -> str:
        if not self._access_token or time.monotonic() >= self._token_expires_at:
            await self._fetch_token()
        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=10.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError, RuntimeError),
    )
    async def get_flight_schedules(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        direct_flights: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch flight schedules from the Lufthansa Operations API.

        Endpoint (LH Public / Open Developer free tier)::

            GET /v1/operations/schedules/{origin}/{destination}/{date}
                ?directFlights=0|1

        Returns a list of schedule objects from the
        ``ScheduleResource.Schedule`` envelope.
        """
        http = await self._ensure_http()
        token = await self._ensure_token()

        date_str = departure_date.isoformat()  # YYYY-MM-DD
        path = f"/v1/operations/schedules/{origin}/{destination}/{date_str}"
        params: dict[str, str] = {
            "directFlights": "1" if direct_flights else "0",
        }

        resp = await http.get(
            path,
            params=params,
            headers=self._auth_headers(token),
        )

        # If 401, refresh token and retry once.
        if resp.status_code == 401:
            logger.warning("Lufthansa token expired, refreshing...")
            await self._fetch_token()
            token = self._access_token
            resp = await http.get(
                path,
                params=params,
                headers=self._auth_headers(token),
            )

        resp.raise_for_status()
        data = resp.json()

        # Response envelope: {"ScheduleResource": {"Schedule": [...]}}
        if isinstance(data, dict):
            resource = data.get("ScheduleResource", data)
            schedules = resource.get("Schedule", [])
            if isinstance(schedules, dict):
                # Single schedule returned as dict instead of list.
                return [schedules]
            return schedules if isinstance(schedules, list) else []
        if isinstance(data, list):
            return data
        return []

    async def health_check(self) -> bool:
        """Verify credentials are valid by obtaining a token."""
        try:
            self._ensure_config()
            await self._ensure_token()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
        self._http = None
        self._access_token = ""
        self._token_expires_at = 0.0
