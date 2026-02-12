"""Airline model."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .flight import Flight
    from .seat_spec import SeatSpec


class AirlineType(enum.StrEnum):
    """Airline service type."""

    FSC = "FSC"
    LCC = "LCC"
    ULCC = "ULCC"


class Alliance(enum.StrEnum):
    """Airline alliance membership."""

    STAR = "Star"
    ONEWORLD = "Oneworld"
    SKYTEAM = "SkyTeam"
    NONE = "None"


class Airline(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Airlines table - stores airline reference data."""

    __tablename__ = "airlines"

    code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[AirlineType] = mapped_column(nullable=False)
    alliance: Mapped[Alliance] = mapped_column(nullable=False, default=Alliance.NONE)
    base_country: Mapped[str] = mapped_column(String(100), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(500))

    # Relationships
    flights: Mapped[list[Flight]] = relationship(back_populates="airline")
    seat_specs: Mapped[list[SeatSpec]] = relationship(back_populates="airline")

    __table_args__ = (Index("ix_airlines_code", "code"),)

    def __repr__(self) -> str:
        return f"<Airline {self.code} ({self.name})>"
