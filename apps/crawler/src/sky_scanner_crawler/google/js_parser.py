"""Parse Google Flights JS-embedded data into NormalizedFlight objects."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from selectolax.lexbor import LexborHTMLParser  # type: ignore[import-untyped]

from sky_scanner_core.schemas import (
    CabinClass,
    DataSource,
    NormalizedFlight,
    NormalizedPrice,
)

from .protobuf_builder import ItinerarySummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Nested-list decoder infrastructure (ported from decoder.py)
# ---------------------------------------------------------------------------

DecodePath = list[int]
type NLBaseType = int | str | None | Sequence[NLBaseType]


@dataclass
class NLData(Sequence[NLBaseType]):
    data: list[NLBaseType]

    def __getitem__(self, decode_path: int | DecodePath) -> NLBaseType:  # type: ignore[override]
        if isinstance(decode_path, int):
            return self.data[decode_path]
        it: Any = self.data
        for index in decode_path:
            assert isinstance(it, list), (
                f"Found non-list type while decoding {decode_path}"
            )
            assert index < len(it), f"Index out of range when decoding {decode_path}"
            it = it[index]
        return it

    def __len__(self) -> int:
        return len(self.data)


@dataclass
class DecoderKey[V]:
    decode_path: DecodePath
    decoder: Callable[[NLData], V] | None = None

    def decode(self, root: NLData) -> NLBaseType | V:
        data = root[self.decode_path]
        if isinstance(data, list) and self.decoder:
            return self.decoder(NLData(data))
        return data


class Decoder:
    @classmethod
    def decode_el(cls, el: NLData) -> Mapping[str, Any]:
        decoded: dict[str, Any] = {}
        for field_name, key_decoder in vars(cls).items():
            if isinstance(key_decoder, DecoderKey):
                decoded[field_name.lower()] = key_decoder.decode(el)
        return decoded

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> Any:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Intermediate dataclasses (mirror reference decoder.py)
# ---------------------------------------------------------------------------


@dataclass
class Codeshare:
    airline_code: str
    flight_number: int
    airline_name: str


@dataclass
class Flight:
    airline: str
    airline_name: str
    flight_number: str
    operator: str
    codeshares: list[Codeshare]
    aircraft: str
    departure_airport: str
    departure_airport_name: str
    arrival_airport: str
    arrival_airport_name: str
    departure_date: tuple[int, int, int]
    arrival_date: tuple[int, int, int]
    departure_time: tuple[int, int]
    arrival_time: tuple[int, int]
    travel_time: int
    seat_pitch_short: str


@dataclass
class Layover:
    minutes: int
    departure_airport: str
    departure_airport_name: str
    departure_airport_city: str
    arrival_airport: str
    arrival_airport_name: str
    arrival_airport_city: str


@dataclass
class Itinerary:
    airline_code: str
    airline_names: list[str]
    flights: list[Flight]
    layovers: list[Layover]
    travel_time: int
    departure_airport: str
    arrival_airport: str
    departure_date: tuple[int, int, int]
    arrival_date: tuple[int, int, int]
    departure_time: tuple[int, int]
    arrival_time: tuple[int, int]
    itinerary_summary: ItinerarySummary


@dataclass
class DecodedResult:
    raw: list[Any]
    best: list[Itinerary]
    other: list[Itinerary]


# ---------------------------------------------------------------------------
# Decoders
# ---------------------------------------------------------------------------


class CodeshareDecoder(Decoder):
    AIRLINE_CODE: DecoderKey[str] = DecoderKey([0])
    FLIGHT_NUMBER: DecoderKey[str] = DecoderKey([1])
    AIRLINE_NAME: DecoderKey[list[str]] = DecoderKey([3])

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> list[Codeshare]:  # type: ignore[override]
        return [Codeshare(**cls.decode_el(NLData(el))) for el in root]  # type: ignore[arg-type]


class FlightDecoder(Decoder):
    OPERATOR: DecoderKey[str] = DecoderKey([2])
    DEPARTURE_AIRPORT: DecoderKey[str] = DecoderKey([3])
    DEPARTURE_AIRPORT_NAME: DecoderKey[str] = DecoderKey([4])
    ARRIVAL_AIRPORT: DecoderKey[str] = DecoderKey([5])
    ARRIVAL_AIRPORT_NAME: DecoderKey[str] = DecoderKey([6])
    DEPARTURE_TIME: DecoderKey[tuple[int, int]] = DecoderKey([8])
    ARRIVAL_TIME: DecoderKey[tuple[int, int]] = DecoderKey([10])
    TRAVEL_TIME: DecoderKey[int] = DecoderKey([11])
    SEAT_PITCH_SHORT: DecoderKey[str] = DecoderKey([14])
    AIRCRAFT: DecoderKey[str] = DecoderKey([17])
    DEPARTURE_DATE: DecoderKey[tuple[int, int, int]] = DecoderKey([20])
    ARRIVAL_DATE: DecoderKey[tuple[int, int, int]] = DecoderKey([21])
    AIRLINE: DecoderKey[str] = DecoderKey([22, 0])
    AIRLINE_NAME: DecoderKey[str] = DecoderKey([22, 3])
    FLIGHT_NUMBER: DecoderKey[str] = DecoderKey([22, 1])
    CODESHARES: DecoderKey[list[Codeshare]] = DecoderKey([15], CodeshareDecoder.decode)

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> list[Flight]:  # type: ignore[override]
        return [Flight(**cls.decode_el(NLData(el))) for el in root]  # type: ignore[arg-type]


class LayoverDecoder(Decoder):
    MINUTES: DecoderKey[int] = DecoderKey([0])
    DEPARTURE_AIRPORT: DecoderKey[str] = DecoderKey([1])
    DEPARTURE_AIRPORT_NAME: DecoderKey[str] = DecoderKey([4])
    DEPARTURE_AIRPORT_CITY: DecoderKey[str] = DecoderKey([5])
    ARRIVAL_AIRPORT: DecoderKey[str] = DecoderKey([2])
    ARRIVAL_AIRPORT_NAME: DecoderKey[str] = DecoderKey([6])
    ARRIVAL_AIRPORT_CITY: DecoderKey[str] = DecoderKey([7])

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> list[Layover]:  # type: ignore[override]
        return [Layover(**cls.decode_el(NLData(el))) for el in root]  # type: ignore[arg-type]


class ItineraryDecoder(Decoder):
    AIRLINE_CODE: DecoderKey[str] = DecoderKey([0, 0])
    AIRLINE_NAMES: DecoderKey[list[str]] = DecoderKey([0, 1])
    FLIGHTS: DecoderKey[list[Flight]] = DecoderKey([0, 2], FlightDecoder.decode)
    DEPARTURE_AIRPORT: DecoderKey[str] = DecoderKey([0, 3])
    DEPARTURE_DATE: DecoderKey[tuple[int, int, int]] = DecoderKey([0, 4])
    DEPARTURE_TIME: DecoderKey[tuple[int, int]] = DecoderKey([0, 5])
    ARRIVAL_AIRPORT: DecoderKey[str] = DecoderKey([0, 6])
    ARRIVAL_DATE: DecoderKey[tuple[int, int, int]] = DecoderKey([0, 7])
    ARRIVAL_TIME: DecoderKey[tuple[int, int]] = DecoderKey([0, 8])
    TRAVEL_TIME: DecoderKey[int] = DecoderKey([0, 9])
    LAYOVERS: DecoderKey[list[Layover]] = DecoderKey([0, 13], LayoverDecoder.decode)
    ITINERARY_SUMMARY: DecoderKey[ItinerarySummary] = DecoderKey(
        [1],
        lambda data: ItinerarySummary.from_b64(data[1]),  # type: ignore[arg-type]
    )

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> list[Itinerary]:  # type: ignore[override]
        return [Itinerary(**cls.decode_el(NLData(el))) for el in root]  # type: ignore[arg-type]


class ResultDecoder(Decoder):
    BEST: DecoderKey[list[Itinerary]] = DecoderKey([2, 0], ItineraryDecoder.decode)
    OTHER: DecoderKey[list[Itinerary]] = DecoderKey([3, 0], ItineraryDecoder.decode)

    @classmethod
    def decode(cls, root: list[Any] | NLData) -> DecodedResult:  # type: ignore[override]
        assert isinstance(root, list), "Root data must be list type"
        return DecodedResult(**cls.decode_el(NLData(root)), raw=root)


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _date_time_to_datetime(
    date_tuple: tuple[int, int, int],
    time_tuple: tuple[int, int],
) -> datetime:
    """Convert (year, month, day) + (hour, minute) tuples to datetime."""
    year, month, day = date_tuple
    hour, minute = time_tuple
    return datetime(year, month, day, hour, minute)


def _itinerary_to_normalized(
    itin: Itinerary,
    cabin_class: CabinClass,
    now: datetime,
) -> list[NormalizedFlight]:
    """Convert an Itinerary into NormalizedFlight objects (one per segment)."""
    results: list[NormalizedFlight] = []
    price_amount = itin.itinerary_summary.price
    currency = itin.itinerary_summary.currency or "USD"

    for flight in itin.flights:
        dep_dt = _date_time_to_datetime(flight.departure_date, flight.departure_time)
        arr_dt = _date_time_to_datetime(flight.arrival_date, flight.arrival_time)

        prices: list[NormalizedPrice] = []
        if price_amount > 0:
            prices.append(
                NormalizedPrice(
                    amount=price_amount,
                    currency=currency,
                    source=DataSource.GOOGLE_PROTOBUF,
                    crawled_at=now,
                )
            )

        results.append(
            NormalizedFlight(
                flight_number=f"{flight.airline}{flight.flight_number}",
                airline_code=flight.airline,
                airline_name=flight.airline_name,
                operator=flight.operator or None,
                origin=flight.departure_airport,
                destination=flight.arrival_airport,
                departure_time=dep_dt,
                arrival_time=arr_dt,
                duration_minutes=flight.travel_time,
                cabin_class=cabin_class,
                aircraft_type=flight.aircraft or None,
                stops=max(0, len(itin.flights) - 1),
                prices=prices,
                source=DataSource.GOOGLE_PROTOBUF,
                crawled_at=now,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_js_data(
    html: str,
    cabin_class: CabinClass = CabinClass.ECONOMY,
) -> list[NormalizedFlight]:
    """Extract JS-embedded flight data from Google Flights HTML.

    Steps:
    1. Parse script.ds:1 content using selectolax
    2. Parse JSON data
    3. Use ResultDecoder to decode
    4. Convert Itinerary objects to NormalizedFlight objects
    """
    parser = LexborHTMLParser(html)
    script_node = parser.css_first(r"script.ds\:1")
    if script_node is None:
        logger.warning("No script.ds:1 found in HTML")
        return []

    script_text = script_node.text()
    match = re.search(r"^.*?\{.*?data:(\[.*\]).*}", script_text)
    if not match:
        logger.warning("Could not extract JS data from script tag")
        return []

    data = json.loads(match.group(1))
    if data is None:
        return []

    decoded = ResultDecoder.decode(data)
    now = datetime.now()

    flights: list[NormalizedFlight] = []
    for itin in decoded.best + decoded.other:
        flights.extend(_itinerary_to_normalized(itin, cabin_class, now))

    logger.info("JS parser extracted %d flights", len(flights))
    return flights
