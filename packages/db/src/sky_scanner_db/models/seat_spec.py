"""Seat specification model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    import uuid

    from .airline import Airline
    from .flight import CabinClass


class SeatSpec(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Seat specs table - stores seat comfort data per airline/aircraft."""

    __tablename__ = "seat_specs"

    airline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("airlines.id"), nullable=False
    )
    aircraft_type: Mapped[str] = mapped_column(String(50), nullable=False)
    cabin_class: Mapped[CabinClass] = mapped_column(nullable=False)
    seat_pitch_inches: Mapped[float | None] = mapped_column(Float)
    seat_width_inches: Mapped[float | None] = mapped_column(Float)
    recline_degrees: Mapped[float | None] = mapped_column(Float)
    has_power_outlet: Mapped[bool] = mapped_column(Boolean, default=False)
    has_usb: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ife: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    airline: Mapped[Airline] = relationship(back_populates="seat_specs")

    __table_args__ = (
        Index("ix_seat_specs_airline_id", "airline_id"),
        Index(
            "ix_seat_specs_airline_aircraft_cabin",
            "airline_id",
            "aircraft_type",
            "cabin_class",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<SeatSpec {self.aircraft_type} {self.cabin_class.value}>"
