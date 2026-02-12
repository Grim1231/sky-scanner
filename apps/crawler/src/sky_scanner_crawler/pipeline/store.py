"""Persist normalized flights into the database."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from sky_scanner_db.models import Airline, Airport
from sky_scanner_db.models import CabinClass as DBCabinClass
from sky_scanner_db.models import DataSource as DBDataSource
from sky_scanner_db.models import Flight as FlightModel
from sky_scanner_db.models import Price as PriceModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from sky_scanner_core.schemas import NormalizedFlight

logger = logging.getLogger(__name__)


class FlightStore:
    """Write NormalizedFlight objects to the flights/prices tables."""

    def __init__(self) -> None:
        self._airline_cache: dict[str, uuid.UUID] = {}
        self._airport_cache: dict[str, uuid.UUID] = {}

    async def _warm_cache(self, session: AsyncSession) -> None:
        """Pre-load airline and airport code-to-UUID maps."""
        rows = (await session.execute(select(Airline.code, Airline.id))).all()
        self._airline_cache = dict(rows)

        rows = (await session.execute(select(Airport.code, Airport.id))).all()
        self._airport_cache = dict(rows)

        logger.debug(
            "Cache warmed: %d airlines, %d airports",
            len(self._airline_cache),
            len(self._airport_cache),
        )

    async def store_flights(
        self,
        flights: list[NormalizedFlight],
        session: AsyncSession,
    ) -> int:
        """Persist a list of normalized flights.  Returns the count stored."""
        if not self._airline_cache and not self._airport_cache:
            await self._warm_cache(session)

        orm_objects: list[FlightModel | PriceModel] = []
        stored = 0

        for nf in flights:
            airline_id = self._airline_cache.get(nf.airline_code)
            if airline_id is None:
                logger.warning(
                    "Unknown airline code %s, skipping flight %s",
                    nf.airline_code,
                    nf.flight_number,
                )
                continue

            origin_id = self._airport_cache.get(nf.origin)
            if origin_id is None:
                logger.warning(
                    "Unknown airport code %s, skipping flight %s",
                    nf.origin,
                    nf.flight_number,
                )
                continue

            dest_id = self._airport_cache.get(nf.destination)
            if dest_id is None:
                logger.warning(
                    "Unknown airport code %s, skipping flight %s",
                    nf.destination,
                    nf.flight_number,
                )
                continue

            flight_id = uuid.uuid4()
            flight_obj = FlightModel(
                id=flight_id,
                airline_id=airline_id,
                flight_number=nf.flight_number,
                origin_airport_id=origin_id,
                destination_airport_id=dest_id,
                departure_time=nf.departure_time,
                arrival_time=nf.arrival_time,
                duration_minutes=nf.duration_minutes,
                aircraft_type=nf.aircraft_type,
                cabin_class=DBCabinClass(nf.cabin_class.value),
                crawled_at=nf.crawled_at,
                source=DBDataSource(nf.source.value),
            )
            orm_objects.append(flight_obj)

            for np in nf.prices:
                price_obj = PriceModel(
                    id=uuid.uuid4(),
                    flight_id=flight_id,
                    price_amount=np.amount,
                    currency=np.currency,
                    fare_class=np.fare_class,
                    includes_baggage=np.includes_baggage,
                    includes_meal=np.includes_meal,
                    seat_selection_included=np.seat_selection_included,
                    crawled_at=np.crawled_at,
                    booking_url=np.booking_url,
                )
                orm_objects.append(price_obj)

            stored += 1

        if orm_objects:
            session.add_all(orm_objects)
            await session.commit()
            logger.info(
                "Stored %d flights (%d ORM objects)",
                stored,
                len(orm_objects),
            )

        return stored
