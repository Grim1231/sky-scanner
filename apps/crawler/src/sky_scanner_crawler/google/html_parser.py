"""Parse Google Flights HTML into NormalizedFlight objects (fallback path)."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from selectolax.lexbor import (  # type: ignore[import-untyped]
    LexborHTMLParser,
    LexborNode,
)

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

logger = logging.getLogger(__name__)


class _Blank:
    """Null-object for missing DOM nodes."""

    def text(self, *_: object, **__: object) -> str:
        return ""

    def iter(self) -> list[object]:
        return []


_blank = _Blank()


def _safe(node: LexborNode | None) -> LexborNode | _Blank:
    return node if node is not None else _blank  # type: ignore[return-value]


def _parse_price(raw: str) -> float:
    """Strip currency symbols and commas, return float."""
    cleaned = re.sub(r"[^\d.]", "", raw.replace(",", ""))
    if not cleaned:
        return 0.0
    return float(cleaned)


def _parse_stops(raw: str) -> int:
    if raw == "Nonstop" or not raw:
        return 0
    try:
        return int(raw.split(" ", 1)[0])
    except ValueError:
        return -1


def parse_html(
    html: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Extract flight data from Google Flights HTML using CSS selectors.

    This is the fallback parser when the JS-embedded data is unavailable.
    It produces less structured data (no per-segment breakdown), so each
    result row maps to a single NormalizedFlight.
    """
    parser = LexborHTMLParser(html)
    now = datetime.now()
    flights: list[NormalizedFlight] = []

    for i, section in enumerate(
        parser.css('div[jsname="IWWDBc"], div[jsname="YdtKid"]')
    ):
        items = section.css("ul.Rk10dc li")
        # For non-best sections, skip the last item (often an ad / promo)
        if i != 0 and len(items) > 1:
            items = items[:-1]

        for item in items:
            name = _safe(item.css_first("div.sSHqwe.tPgKwe.ogfYpf span")).text(
                strip=True
            )
            if not name:
                continue

            # Departure & arrival times (extracted but not used in HTML
            # fallback since we lack structured time data)
            dp_ar_nodes = item.css("span.mv1WYe div")
            try:
                _ = dp_ar_nodes[0].text(strip=True)
                _ = dp_ar_nodes[1].text(strip=True)
            except (IndexError, AttributeError):
                pass

            # Duration
            duration_text = _safe(item.css_first("li div.Ak5kof div")).text()

            # Stops
            stops_text = _safe(item.css_first(".BbR8Ec .ogfYpf")).text()
            stops = _parse_stops(stops_text)

            # Price
            price_text = _safe(item.css_first(".YMlIz.FpEdX")).text() or "0"
            price_amount = _parse_price(price_text)

            # Parse duration into minutes (e.g. "12 hr 30 min" -> 750)
            duration_minutes = 0
            hr_match = re.search(r"(\d+)\s*hr", duration_text)
            min_match = re.search(r"(\d+)\s*min", duration_text)
            if hr_match:
                duration_minutes += int(hr_match.group(1)) * 60
            if min_match:
                duration_minutes += int(min_match.group(1))

            # Extract airline code from name (first 2 chars if looks like code)
            airline_code = name[:2] if len(name) >= 2 else name

            prices: list[NormalizedPrice] = []
            if price_amount > 0:
                prices.append(
                    NormalizedPrice(
                        amount=price_amount,
                        currency="USD",
                        source=DataSource.GOOGLE_PROTOBUF,
                        crawled_at=now,
                    )
                )

            flights.append(
                NormalizedFlight(
                    flight_number=name,
                    airline_code=airline_code,
                    airline_name=name,
                    origin="",
                    destination="",
                    departure_time=now,
                    arrival_time=now,
                    duration_minutes=duration_minutes,
                    cabin_class=cabin_class,
                    stops=stops if stops >= 0 else 0,
                    prices=prices,
                    source=DataSource.GOOGLE_PROTOBUF,
                    crawled_at=now,
                )
            )

    logger.info("HTML parser extracted %d flights", len(flights))
    return flights
