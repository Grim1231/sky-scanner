"""HTTP client for Hainan Airlines' mobile fare-trends API.

Uses the ``app.hnair.com`` ``airFareTrends`` endpoint, which returns
daily lowest fares for domestic Chinese routes.  Every request must
carry an HMAC-SHA1 signature (``hnairSign`` query parameter) computed
from the merged common + data payload.

.. note::
   This endpoint only supports **domestic** Chinese routes (e.g.
   PEK-HAK, PEK-CAN).  International routes return an empty result.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from typing import Any

import httpx

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://app.hnair.com"
_FARE_TRENDS_PATH = "/ticket/faretrend/airFareTrends"

# Signing constants extracted from the mobile web bundle (m.hnair.com).
_CERTIFICATE_HASH = "6093941774D84495A5D15D8F909CAA1E"
_HARD_CODE = "21047C596EAD45209346AE29F0350491"
_APP_KEY = "9E4BBDDEC6C8416EA380E418161A7CD3"

# Cabin mapping: our CabinClass enum -> Hainan Airlines cabin code.
_CABIN_MAP: dict[str, str] = {
    "ECONOMY": "Y",
    "PREMIUM_ECONOMY": "Y",  # no separate PE cabin in the API
    "BUSINESS": "C",
    "FIRST": "F",
}


def _make_device_id() -> str:
    """Generate a random device ID (UUID without dashes)."""
    return uuid.uuid4().hex.upper()


def _make_common(device_id: str, timestamp_ms: int) -> dict[str, Any]:
    """Build the ``common`` envelope header."""
    return {
        "sname": "MacIntel",
        "sver": (
            "5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        "schannel": "HTML5",
        "caller": "HTML5",
        "slang": "zh-CN",
        "did": device_id,
        "stime": timestamp_ms,
        "szone": -480,
        "aname": "com.hnair.spa.web.standard",
        "aver": "10.11.0",
        "akey": _APP_KEY,
        "abuild": "1",
        "atarget": "standard",
        "slat": "slat",
        "slng": "slng",
        "gtcid": "defualt_web_gtcid",
        "riskToken": "",
        "captchaToken": "",
        "blackBox": "",
        "validateToken": "",
    }


def _make_sign(merged_params: dict[str, Any]) -> str:
    """Compute the HMAC-SHA1 signature required by Hainan Airlines.

    Algorithm (reverse-engineered from the mobile web bundle):
      1. Sort all keys in ``merged_params`` alphabetically.
      2. For each key whose value is a primitive (str/int/float/bool),
         append the stringified value to a buffer.
      3. Append ``_CERTIFICATE_HASH``.
      4. HMAC-SHA1 the buffer using ``_HARD_CODE`` as the key.
      5. Return uppercase hex digest.
    """
    values: list[str] = []
    for key in sorted(merged_params.keys()):
        val = merged_params[key]
        if isinstance(val, bool):
            values.append(str(val).lower())
        elif isinstance(val, (str, int, float)):
            values.append(str(val))

    message = "".join(values) + _CERTIFICATE_HASH
    sig = hmac.new(
        _HARD_CODE.encode(),
        message.encode(),
        hashlib.sha1,
    ).hexdigest()
    return sig.upper()


class HainanAirlinesClient:
    """Async wrapper around Hainan Airlines' fare-trends API."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._device_id = _make_device_id()
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Content-Type": "application/json",
                "Origin": "https://m.hnair.com",
                "Referer": "https://m.hnair.com/",
                "appver": "10.11.0",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            },
            timeout=httpx.Timeout(timeout),
        )

    @async_retry(
        max_retries=2,
        base_delay=1.0,
        max_delay=15.0,
        exceptions=(httpx.HTTPStatusError, httpx.TransportError),
    )
    async def search_fare_trends(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        cabin: str = "Y",
    ) -> dict[str, Any]:
        """Fetch the fare-trend price calendar for a route.

        Parameters
        ----------
        origin:
            3-letter IATA code (e.g. ``PEK``).
        destination:
            3-letter IATA code (e.g. ``HAK``).
        departure_date:
            ISO date string ``YYYY-MM-DD``.
        cabin:
            Hainan cabin code: ``Y`` (economy), ``C`` (business),
            ``F`` (first).

        Returns
        -------
        dict
            Raw JSON response from the API.

        Raises
        ------
        RuntimeError
            If the API returns ``success: false``.
        """
        timestamp_ms = int(time.time() * 1000)
        common = _make_common(self._device_id, timestamp_ms)

        data: dict[str, Any] = {
            "orgCode": origin,
            "dstCode": destination,
            "depDate": departure_date,
            "cabin": cabin,
            "isOrgCity": "true",
            "isDstCity": "true",
            "_referer": "",
        }

        # Merge common + data for signing (flat dict).
        merged: dict[str, Any] = {}
        merged.update(common)
        merged.update(data)

        sign = _make_sign(merged)

        body = {"common": common, "data": data}

        resp = await self._client.post(
            _FARE_TRENDS_PATH,
            params={"hnairSign": sign},
            content=json.dumps(body),
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()

        if not result.get("success"):
            msg = result.get("message", "Unknown error")
            raise RuntimeError(f"Hainan Airlines API error: {msg}")

        inner = result.get("data", {})
        calendar = inner.get("priceCalandar", [])  # sic: API typo
        logger.debug(
            "Hainan Airlines fare trends %s->%s (%s): %d days",
            origin,
            destination,
            departure_date,
            len(calendar),
        )
        return result

    async def health_check(self) -> bool:
        """Check if the Hainan Airlines fare-trends API is reachable."""
        try:
            result = await self.search_fare_trends(
                origin="PEK",
                destination="HAK",
                departure_date="2026-04-01",
                cabin="Y",
            )
            return result.get("success", False)
        except Exception:
            return False

    async def close(self) -> None:
        """Shut down the underlying HTTPX client."""
        await self._client.aclose()
