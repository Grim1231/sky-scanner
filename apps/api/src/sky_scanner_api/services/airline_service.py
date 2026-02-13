"""Airline listing service."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from sky_scanner_db.models import Airline

from ..schemas.airlines import AirlineItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class AirlineService:
    """Handles airline listing queries."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_airlines(
        self,
        type_filter: str | None = None,
        alliance_filter: str | None = None,
    ) -> list[AirlineItem]:
        stmt = select(Airline)

        if type_filter is not None:
            stmt = stmt.where(Airline.type == type_filter)
        if alliance_filter is not None:
            stmt = stmt.where(Airline.alliance == alliance_filter)

        stmt = stmt.order_by(Airline.name)

        result = await self._db.execute(stmt)
        airlines = result.scalars().all()

        return [
            AirlineItem(
                code=al.code,
                name=al.name,
                type=al.type.value,
                alliance=al.alliance.value,
                base_country=al.base_country,
                website_url=al.website_url,
            )
            for al in airlines
        ]
