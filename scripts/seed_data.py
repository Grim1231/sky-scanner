"""Load seed data from data/seed/*.json into the database."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add packages to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "db" / "src"))

from sky_scanner_db.models.airline import Airline, AirlineType, Alliance  # noqa: E402
from sky_scanner_db.models.airport import Airport  # noqa: E402
from sky_scanner_db.models.flight import CabinClass  # noqa: E402
from sky_scanner_db.models.seat_spec import SeatSpec  # noqa: E402

SEED_DIR = PROJECT_ROOT / "data" / "seed"

ALLIANCE_MAP = {
    "Star Alliance": Alliance.STAR,
    "Oneworld": Alliance.ONEWORLD,
    "SkyTeam": Alliance.SKYTEAM,
    "None": Alliance.NONE,
    "": Alliance.NONE,
}

CABIN_MAP = {
    "ECONOMY": CabinClass.ECONOMY,
    "PREMIUM_ECONOMY": CabinClass.PREMIUM_ECONOMY,
    "BUSINESS": CabinClass.BUSINESS,
    "FIRST": CabinClass.FIRST,
}


async def load_airlines(session: AsyncSession) -> dict[str, Airline]:
    """Load airlines and return code→Airline mapping."""
    existing = (await session.execute(select(Airline))).scalars().all()
    if existing:
        print(f"  Airlines already loaded ({len(existing)} rows), skipping.")
        return {a.code: a for a in existing}

    with open(SEED_DIR / "airlines.json") as f:
        data = json.load(f)

    airlines: dict[str, Airline] = {}
    for item in data:
        airline = Airline(
            code=item["code"],
            name=item["name"],
            type=AirlineType(item["type"]),
            alliance=ALLIANCE_MAP.get(item.get("alliance", "None"), Alliance.NONE),
            base_country=item["country"],
            website_url=item.get("website_url"),
        )
        session.add(airline)
        airlines[item["code"]] = airline

    await session.flush()
    print(f"  Loaded {len(airlines)} airlines.")
    return airlines


async def load_airports(session: AsyncSession) -> int:
    """Load airports, return count."""
    existing = (await session.execute(select(Airport))).scalars().all()
    if existing:
        print(f"  Airports already loaded ({len(existing)} rows), skipping.")
        return len(existing)

    with open(SEED_DIR / "airports.json") as f:
        data = json.load(f)

    for item in data:
        session.add(
            Airport(
                code=item["code"],
                name=item["name"],
                city=item["city"],
                country=item["country"],
                timezone=item["timezone"],
                latitude=item["latitude"],
                longitude=item["longitude"],
            )
        )

    await session.flush()
    print(f"  Loaded {len(data)} airports.")
    return len(data)


async def load_seat_specs(session: AsyncSession, airlines: dict[str, Airline]) -> int:
    """Load seat specs, return count."""
    existing = (await session.execute(select(SeatSpec))).scalars().all()
    if existing:
        print(f"  Seat specs already loaded ({len(existing)} rows), skipping.")
        return len(existing)

    with open(SEED_DIR / "seat_specs.json") as f:
        data = json.load(f)

    count = 0
    for item in data:
        airline = airlines.get(item["airline_code"])
        if not airline:
            code = item["airline_code"]
            print(f"  Warning: airline {code} not found, skipping.")
            continue
        session.add(
            SeatSpec(
                airline_id=airline.id,
                aircraft_type=item["aircraft_type"],
                cabin_class=CABIN_MAP[item["cabin_class"]],
                seat_pitch_inches=item.get("seat_pitch_inches"),
                seat_width_inches=item.get("seat_width_inches"),
                recline_degrees=item.get("recline_degrees"),
                has_power_outlet=item.get("has_power_outlet", False),
                has_usb=item.get("has_usb", False),
                has_ife=item.get("has_ife", False),
            )
        )
        count += 1

    await session.flush()
    print(f"  Loaded {count} seat specs.")
    return count


async def main() -> None:
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://skyscanner:skyscanner_dev@localhost:5432/skyscanner",
    )
    engine = create_async_engine(database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    print("Seeding database...")
    async with session_factory() as session, session.begin():
        print("[1/3] Airlines...")
        airlines = await load_airlines(session)
        print("[2/3] Airports...")
        await load_airports(session)
        print("[3/3] Seat Specs...")
        await load_seat_specs(session, airlines)

    await engine.dispose()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
