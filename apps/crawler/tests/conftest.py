"""Shared fixtures and helpers for crawler E2E tests."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

from sky_scanner_core.schemas import CabinClass, CrawlTask, DataSource, SearchRequest

if TYPE_CHECKING:
    from sky_scanner_core.schemas import CrawlResult


@pytest.fixture
def future_date() -> date:
    """Return a date ~30 days from now (avoids past-date errors)."""
    return date.today() + timedelta(days=30)


@pytest.fixture
def make_task(future_date: date):
    """Factory fixture for creating CrawlTask instances."""

    def _make(
        origin: str,
        destination: str,
        departure_date: date | None = None,
        cabin: CabinClass = CabinClass.ECONOMY,
        source: DataSource = DataSource.DIRECT_CRAWL,
    ) -> CrawlTask:
        return CrawlTask(
            search_request=SearchRequest(
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=departure_date or future_date,
                cabin_class=cabin,
            ),
            source=source,
        )

    return _make


def assert_crawl_result(
    result: CrawlResult,
    *,
    min_flights: int = 1,
    allow_no_prices: bool = False,
) -> None:
    """Validate a CrawlResult has expected structure."""
    assert result.success is True, f"Crawl failed: {result.error}"
    assert result.error is None
    assert result.duration_ms > 0
    assert len(result.flights) >= min_flights, (
        f"Expected >= {min_flights} flights, got {len(result.flights)}"
    )
    for flight in result.flights:
        assert len(flight.origin) == 3, f"Bad origin: {flight.origin}"
        assert len(flight.destination) == 3, f"Bad dest: {flight.destination}"
        assert flight.airline_code, "Missing airline_code"
        if not allow_no_prices:
            assert len(flight.prices) > 0 or flight.departure_time, (
                "Flight has no prices and no departure_time"
            )
