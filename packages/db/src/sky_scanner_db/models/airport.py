"""Airport model."""

from __future__ import annotations

from sqlalchemy import Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Airport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Airports table - stores airport reference data."""

    __tablename__ = "airports"

    code: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_airports_code", "code"),
        Index("ix_airports_city", "city"),
        Index("ix_airports_country", "country"),
    )

    def __repr__(self) -> str:
        return f"<Airport {self.code} ({self.city})>"
