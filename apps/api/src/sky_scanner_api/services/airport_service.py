"""Airport search service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import case, or_, select

from sky_scanner_db.models import Airport

from ..schemas.airports import AirportItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AirportService:
    """Handles airport search queries."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def search_airports(
        self,
        query: str,
        limit: int = 10,
    ) -> list[AirportItem]:
        pattern = f"%{query}%"

        exact_code_match = case(
            (Airport.code == query.upper(), 0),
            else_=1,
        )

        stmt = (
            select(Airport)
            .where(
                or_(
                    Airport.code.ilike(pattern),
                    Airport.name.ilike(pattern),
                    Airport.city.ilike(pattern),
                )
            )
            .order_by(exact_code_match, Airport.name)
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        airports = result.scalars().all()

        return [
            AirportItem(
                code=ap.code,
                name=ap.name,
                city=ap.city,
                country=ap.country,
                timezone=ap.timezone,
                latitude=ap.latitude,
                longitude=ap.longitude,
            )
            for ap in airports
        ]
