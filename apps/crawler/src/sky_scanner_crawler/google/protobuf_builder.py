"""Build Google Flights protobuf TFS query parameters."""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

from sky_scanner_core.schemas import CabinClass, SearchRequest, TripType

from .proto import flights_pb2 as PB  # type: ignore  # noqa: N812

logger = logging.getLogger(__name__)

# Mappings from our enums to protobuf enum values
_CABIN_TO_PB_SEAT: dict[CabinClass, Any] = {
    CabinClass.ECONOMY: PB.Seat.ECONOMY,
    CabinClass.PREMIUM_ECONOMY: PB.Seat.PREMIUM_ECONOMY,
    CabinClass.BUSINESS: PB.Seat.BUSINESS,
    CabinClass.FIRST: PB.Seat.FIRST,
}

_TRIP_TO_PB_TRIP: dict[TripType, Any] = {
    TripType.ROUND_TRIP: PB.Trip.ROUND_TRIP,
    TripType.ONE_WAY: PB.Trip.ONE_WAY,
    TripType.MULTI_CITY: PB.Trip.MULTI_CITY,
}


@dataclass
class ItinerarySummary:
    """Decoded itinerary summary from protobuf."""

    flights: str
    price: float
    currency: str

    @classmethod
    def from_b64(cls, b64_string: str) -> ItinerarySummary:
        raw = base64.b64decode(b64_string)
        pb = PB.ItinerarySummary()
        pb.ParseFromString(raw)
        return cls(pb.flights, pb.price.price / 100, pb.price.currency)


class FlightData:
    """A single leg of a flight query (origin -> destination on a date)."""

    __slots__ = ("date", "from_airport", "max_stops", "to_airport")

    def __init__(
        self,
        *,
        date: str,
        from_airport: str,
        to_airport: str,
        max_stops: int | None = None,
    ) -> None:
        self.date = date
        self.from_airport = from_airport
        self.to_airport = to_airport
        self.max_stops = max_stops

    def attach(self, info: Any) -> None:
        data = info.data.add()
        data.date = self.date
        data.from_flight.airport = self.from_airport
        data.to_flight.airport = self.to_airport
        if self.max_stops is not None:
            data.max_stops = self.max_stops


class Passengers:
    """Maps passenger counts to protobuf Passenger enum list."""

    def __init__(
        self,
        *,
        adults: int = 1,
        children: int = 0,
        infants_in_seat: int = 0,
        infants_on_lap: int = 0,
    ) -> None:
        self._pb: list[Any] = []
        self._pb += [PB.Passenger.ADULT] * adults
        self._pb += [PB.Passenger.CHILD] * children
        self._pb += [PB.Passenger.INFANT_IN_SEAT] * infants_in_seat
        self._pb += [PB.Passenger.INFANT_ON_LAP] * infants_on_lap

    def attach(self, info: Any) -> None:
        for p in self._pb:
            info.passengers.append(p)


class TFSData:
    """Builds the ``?tfs=`` protobuf parameter for Google Flights."""

    def __init__(
        self,
        *,
        flight_data: list[FlightData],
        seat: Any,
        trip: Any,
        passengers: Passengers,
    ) -> None:
        self.flight_data = flight_data
        self.seat = seat
        self.trip = trip
        self.passengers = passengers

    def _build_pb(self) -> Any:
        info = PB.Info()
        info.seat = self.seat
        info.trip = self.trip
        self.passengers.attach(info)
        for fd in self.flight_data:
            fd.attach(info)
        return info

    def to_bytes(self) -> bytes:
        return self._build_pb().SerializeToString()

    def as_b64(self) -> bytes:
        return base64.b64encode(self.to_bytes())

    @classmethod
    def from_search_request(cls, req: SearchRequest) -> TFSData:
        """Build TFSData from a SearchRequest."""
        seat = _CABIN_TO_PB_SEAT[req.cabin_class]
        trip = _TRIP_TO_PB_TRIP[req.trip_type]
        passengers = Passengers(
            adults=req.passengers.adults,
            children=req.passengers.children,
            infants_in_seat=req.passengers.infants_in_seat,
            infants_on_lap=req.passengers.infants_on_lap,
        )

        legs = [
            FlightData(
                date=req.departure_date.strftime("%Y-%m-%d"),
                from_airport=req.origin,
                to_airport=req.destination,
            )
        ]
        if req.trip_type == TripType.ROUND_TRIP and req.return_date:
            legs.append(
                FlightData(
                    date=req.return_date.strftime("%Y-%m-%d"),
                    from_airport=req.destination,
                    to_airport=req.origin,
                )
            )

        return cls(
            flight_data=legs,
            seat=seat,
            trip=trip,
            passengers=passengers,
        )
