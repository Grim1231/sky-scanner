"""L2 primp-based HTTP client for Air Premia's fare API.

Replaces the L3 Playwright-assisted client with direct ``primp`` calls
using Chrome TLS impersonation.  This avoids the TLS fingerprint mismatch
that causes intermittent 403s when Playwright obtains a ``cf_clearance``
cookie but ``httpx`` presents a different JA3 fingerprint.

Strategy:
1. Create a fresh ``primp.Client`` with ``impersonate="chrome_131"``
2. Warm up with a GET to ``https://www.airpremia.com/`` (collects CF cookies)
3. Call ``/api/v1/low-fares`` with query parameters
4. All blocking I/O runs via ``asyncio.to_thread()``

Date alignment:
    Air Premia's ``/api/v1/low-fares`` requires **month-aligned** date
    ranges:  the end date must be the last day of its calendar month, and
    each request can span at most two consecutive months.  Arbitrary date
    ranges are automatically split into valid month-aligned chunks, fetched
    individually, and merged back together.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
from datetime import date, timedelta
from typing import Any

import primp

from sky_scanner_crawler.retry import async_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.airpremia.com"


def _last_day_of_month(year: int, month: int) -> date:
    """Return the last day of the given *year*/*month*."""
    _, day = calendar.monthrange(year, month)
    return date(year, month, day)


def _month_aligned_chunks(
    begin: date,
    end: date,
) -> list[tuple[date, date]]:
    """Split ``[begin, end]`` into Air Premia-compatible chunks.

    Each chunk satisfies two constraints enforced by the API:
    * The end date is the last calendar day of its month.
    * The chunk spans at most two consecutive months (e.g. Mar 15 -- Apr 30).

    Returns a list of ``(chunk_begin, chunk_end)`` tuples that together
    cover the full ``[begin, end]`` interval.
    """
    chunks: list[tuple[date, date]] = []
    cursor = begin

    while cursor <= end:
        # End of the current month.
        eom = _last_day_of_month(cursor.year, cursor.month)

        if eom >= end:
            # The remaining range fits within one month.
            chunks.append((cursor, eom))
            break

        # Try extending to the end of the *next* month (2-month span).
        if cursor.month == 12:
            next_eom = _last_day_of_month(cursor.year + 1, 1)
        else:
            next_eom = _last_day_of_month(cursor.year, cursor.month + 1)

        if next_eom >= end:
            chunks.append((cursor, next_eom))
            break

        # Take a 2-month chunk and advance.
        chunks.append((cursor, next_eom))
        # Next chunk starts on the first day of the month after next_eom.
        if next_eom.month == 12:
            cursor = date(next_eom.year + 1, 1, 1)
        else:
            cursor = date(next_eom.year, next_eom.month + 1, 1)

    return chunks


class AirPremiaL2Client:
    """Async wrapper around Air Premia's ``/api/v1/low-fares`` using primp.

    Each API call creates a fresh ``primp.Client`` so Cloudflare doesn't
    track and block a persistent session.  The ``cookie_store=True`` option
    lets primp automatically store and forward cookies set during the
    warm-up GET (including ``cf_clearance``).
    """

    def __init__(self, *, timeout: int = 30) -> None:
        self._timeout = timeout

    def _new_client(self) -> primp.Client:
        """Create a fresh primp client with Chrome TLS impersonation."""
        return primp.Client(
            impersonate="chrome_131",
            follow_redirects=True,
            cookie_store=True,
            timeout=self._timeout,
        )

    def _warm_and_get(
        self,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """Warm up with homepage GET, then call the API.

        Creates a fresh primp client each time to avoid fingerprint
        staleness and CF tracking issues.
        """
        client = self._new_client()

        # Warm up -- visit homepage to collect CF cookies
        warmup = client.get(_BASE_URL)
        logger.debug(
            "Air Premia warmup: %s %d",
            warmup.url,
            warmup.status_code,
        )

        resp = client.get(
            f"{_BASE_URL}{path}",
            params=params,
            headers={
                "Accept": "application/json",
                "Referer": f"{_BASE_URL}/",
            },
        )

        if resp.status_code == 403:
            msg = f"Air Premia API {path}: HTTP 403 (CF blocked)"
            raise RuntimeError(msg)
        if resp.status_code != 200:
            msg = f"Air Premia API {path}: HTTP {resp.status_code}"
            raise RuntimeError(msg)

        result: dict[str, Any] = resp.json()
        return result

    @async_retry(
        max_retries=3,
        base_delay=2.0,
        max_delay=20.0,
        exceptions=(RuntimeError, OSError),
    )
    async def _fetch_chunk(
        self,
        origin: str,
        destination: str,
        begin_date: str,
        end_date: str,
        trip_type: str,
        adt_count: int,
    ) -> dict[str, Any]:
        """Fetch a single month-aligned chunk from the low-fares API."""
        params = {
            "origin": origin,
            "destination": destination,
            "beginDate": begin_date,
            "endDate": end_date,
            "tripType": trip_type,
            "adtCount": str(adt_count),
        }
        result = await asyncio.to_thread(
            self._warm_and_get,
            "/api/v1/low-fares",
            params,
        )
        logger.debug(
            "Air Premia L2 chunk %s->%s (%s ~ %s): %d result groups",
            origin,
            destination,
            begin_date,
            end_date,
            len(result.get("results", [])),
        )
        return result

    async def get_low_fares(
        self,
        origin: str,
        destination: str,
        begin_date: str,
        end_date: str,
        trip_type: str = "OW",
        adt_count: int = 1,
    ) -> dict[str, Any]:
        """Fetch daily lowest fares for a route/date range.

        The Air Premia low-fares API requires the end date to be the last
        calendar day of its month and each request to span at most two
        months.  This method transparently splits arbitrary date ranges
        into valid chunks, fetches each one, and merges the results.

        Parameters
        ----------
        origin:
            IATA station code (e.g. ``ICN``).
        destination:
            IATA station code (e.g. ``HNL``).
        begin_date:
            Start date as ``YYYY-MM-DD``.
        end_date:
            End date as ``YYYY-MM-DD``.
        trip_type:
            ``OW`` (one-way) or ``RT`` (round-trip).
        adt_count:
            Number of adult passengers.

        Returns
        -------
        dict
            Merged JSON response from the Air Premia low-fares API.
        """
        begin = date.fromisoformat(begin_date)
        end = date.fromisoformat(end_date)

        chunks = _month_aligned_chunks(begin, end)
        logger.debug(
            "Air Premia date range %s ~ %s split into %d chunk(s)",
            begin_date,
            end_date,
            len(chunks),
        )

        # Fetch all chunks (sequentially to avoid CF rate-limiting).
        all_availabilities: list[dict[str, Any]] = []
        for chunk_begin, chunk_end in chunks:
            chunk_result = await self._fetch_chunk(
                origin=origin,
                destination=destination,
                begin_date=chunk_begin.isoformat(),
                end_date=chunk_end.isoformat(),
                trip_type=trip_type,
                adt_count=adt_count,
            )
            for result_group in chunk_result.get("results", []):
                all_availabilities.extend(
                    result_group.get("dailyLowFareAvailabilities", []),
                )

        # Filter to only include days within the originally requested range.
        filtered: list[dict[str, Any]] = []
        for day in all_availabilities:
            day_date_str = day.get("date", "")
            if not day_date_str:
                continue
            try:
                day_date = date.fromisoformat(day_date_str)
            except (ValueError, TypeError):
                continue
            if begin <= day_date <= end:
                filtered.append(day)

        # Reconstruct a response in the same format the parser expects.
        merged: dict[str, Any] = {
            "results": [
                {
                    "origin": origin,
                    "destination": destination,
                    "dailyLowFareAvailabilities": filtered,
                },
            ],
        }

        logger.info(
            "Air Premia L2 %s->%s (%s ~ %s): %d days from %d chunk(s)",
            origin,
            destination,
            begin_date,
            end_date,
            len(filtered),
            len(chunks),
        )
        return merged

    async def search_low_fares(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        *,
        days: int = 30,
        trip_type: str = "OW",
        adt_count: int = 1,
    ) -> dict[str, Any]:
        """Convenience method: search low fares for a date range.

        Parameters
        ----------
        origin:
            IATA code (e.g. ``ICN``).
        destination:
            IATA code (e.g. ``HNL``).
        departure_date:
            Start date.
        days:
            Number of days to search ahead (default 30).
        trip_type:
            ``OW`` or ``RT``.
        adt_count:
            Number of adult passengers.

        Returns
        -------
        dict
            Raw JSON response from the API.
        """
        begin = departure_date.isoformat()
        end = (departure_date + timedelta(days=days)).isoformat()
        return await self.get_low_fares(
            origin=origin,
            destination=destination,
            begin_date=begin,
            end_date=end,
            trip_type=trip_type,
            adt_count=adt_count,
        )

    async def get_airports(self) -> list[dict[str, Any]]:
        """Fetch all active airports (no CF protection needed)."""
        client = self._new_client()
        resp = await asyncio.to_thread(
            lambda: client.get(
                f"{_BASE_URL}/api/v1/airports",
                params={"isActive": "true"},
                headers={"Accept": "application/json"},
            ),
        )
        if resp.status_code != 200:
            msg = f"Air Premia airports: HTTP {resp.status_code}"
            raise RuntimeError(msg)
        data: list[dict[str, Any]] = resp.json()
        return data

    async def health_check(self) -> bool:
        """Check if the Air Premia API is reachable."""
        try:
            airports = await self.get_airports()
            return len(airports) > 0
        except Exception:
            return False

    async def close(self) -> None:
        """No-op -- each request creates a fresh primp client."""
