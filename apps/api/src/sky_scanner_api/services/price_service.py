"""Price history service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import cast, func, select
from sqlalchemy.types import Date

from sky_scanner_db.models import Airport, CabinClass, Flight, Price

from ..schemas.prices import PricePoint

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


class PriceService:
    """Handles price history queries."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_price_history(
        self,
        origin: str,
        destination: str,
        start_date: date,
        end_date: date,
        cabin_class: CabinClass,
        currency: str = "KRW",
    ) -> list[PricePoint]:
        origin_ap = Airport.__table__.alias("origin_ap")
        dest_ap = Airport.__table__.alias("dest_ap")

        flight_date = cast(Flight.departure_time, Date).label("flight_date")

        stmt = (
            select(
                flight_date,
                func.min(Price.price_amount).label("min_price"),
                func.max(Price.price_amount).label("max_price"),
                func.avg(Price.price_amount).label("avg_price"),
                func.count().label("sample_count"),
            )
            .join(Flight, Price.flight_id == Flight.id)
            .join(origin_ap, Flight.origin_airport_id == origin_ap.c.id)
            .join(dest_ap, Flight.destination_airport_id == dest_ap.c.id)
            .where(
                origin_ap.c.code == origin,
                dest_ap.c.code == destination,
                Flight.departure_time >= start_date,
                Flight.departure_time <= end_date,
                Flight.cabin_class == cabin_class,
                Price.currency == currency,
            )
            .group_by(flight_date)
            .order_by(flight_date)
        )

        result = await self._db.execute(stmt)
        rows = result.all()

        return [
            PricePoint(
                date=row.flight_date,
                min_price=float(row.min_price),
                max_price=float(row.max_price),
                avg_price=float(row.avg_price),
                currency=currency,
                sample_count=row.sample_count,
            )
            for row in rows
        ]
