"""CLI for standalone crawler testing."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env before any module reads os.getenv (e.g. sky_scanner_db.database).
# Walk up from CWD to find the project-root .env file.
_env_path = Path.cwd() / ".env"
if not _env_path.exists():
    # Fallback: resolve relative to this source file (../../../../../../.env)
    _env_path = Path(__file__).resolve().parents[4] / ".env"
load_dotenv(_env_path, override=False)

from sky_scanner_core.schemas import (  # noqa: E402
    CabinClass,
    CrawlTask,
    DataSource,
    SearchRequest,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _build_search_request(
    origin: str, destination: str, departure_date: str, cabin: str
) -> SearchRequest:
    return SearchRequest(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=date.fromisoformat(departure_date),
        cabin_class=CabinClass(cabin.upper()),
    )


def _store_to_db(flights: list) -> None:  # type: ignore[type-arg]
    """Persist crawled flights to the database."""
    from .pipeline.store import FlightStore

    async def _run() -> int:
        from sky_scanner_db.database import async_session_factory

        store = FlightStore()
        async with async_session_factory() as session:
            count = await store.store_flights(flights, session)
            return count

    count = asyncio.run(_run())
    click.echo(f"Stored {count} flights to database.")


def _print_results(flights: list) -> None:  # type: ignore[type-arg]
    if not flights:
        click.echo("No flights found.")
        return
    click.echo(f"\nFound {len(flights)} flight(s):\n")
    for i, f in enumerate(flights, 1):
        prices_str = ", ".join(
            f"{p.amount} {p.currency} ({p.source.value})" for p in f.prices
        )
        click.echo(
            f"  {i}. {f.flight_number} | {f.origin} → {f.destination} | "
            f"{f.departure_time:%H:%M} - {f.arrival_time:%H:%M} | "
            f"{f.duration_minutes}min | {f.stops} stop(s) | "
            f"Prices: [{prices_str}]"
        )


@click.group()
def cli() -> None:
    """Sky Scanner Crawler CLI."""


@cli.command("crawl-l1")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_l1(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L1: Google Flights Protobuf crawl."""
    from .google.crawler import GoogleFlightsCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.GOOGLE_PROTOBUF)

    async def _run():  # type: ignore[return]
        crawler = GoogleFlightsCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-l2")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def crawl_l2(
    origin: str, destination: str, departure_date: str, cabin: str, json_output: bool
) -> None:
    """L2: Kiwi Tequila API crawl."""
    from .kiwi.crawler import KiwiCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.KIWI_API)

    async def _run():  # type: ignore[return]
        crawler = KiwiCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)


@cli.command("crawl-jeju")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_jeju(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Jeju Air lowest-fare calendar crawl."""
    from .jeju_air.crawler import JejuAirCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = JejuAirCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-eastar")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_eastar(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Eastar Jet daily lowest-fare crawl."""
    from .eastar_jet.crawler import EastarJetCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = EastarJetCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-premia")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_premia(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L3: Air Premia lowest-fare crawl (Playwright-assisted)."""
    from .air_premia.crawler import AirPremiaCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AirPremiaCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-jin-air")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_jin_air(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Jin Air daily lowest fares from S3 bucket."""
    from .jin_air.crawler import JinAirCrawler

    # Jin Air returns all available dates, no specific date needed
    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(
        search_request=search_req,
        source=DataSource.DIRECT_CRAWL,
    )

    async def _run():  # type: ignore[return]
        crawler = JinAirCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-tway")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_tway(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: T'way Air daily fares via agency portal."""
    from .tway_air.crawler import TwayAirCrawler

    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(
        search_request=search_req,
        source=DataSource.DIRECT_CRAWL,
    )

    async def _run():  # type: ignore[return]
        crawler = TwayAirCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-air-seoul")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_air_seoul(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Air Seoul flight search via primp TLS fingerprint."""
    from .air_seoul.crawler import AirSeoulCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AirSeoulCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-air-busan")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_air_busan(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Air Busan flights via Naver Yeti UA bypass."""
    from .air_busan.crawler import AirBusanCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AirBusanCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-lufthansa")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_lufthansa(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Lufthansa Group flight schedules (LH/LX/OS/4U/SN/EN/WK/4Y)."""
    from .lufthansa_group.crawler import LufthansaCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = LufthansaCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-singapore")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_singapore(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Singapore Airlines flight availability via NDC API (SQ)."""
    from .singapore_airlines.crawler import SingaporeAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = SingaporeAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-afklm")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_afklm(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L3: Air France-KLM flight offers via Playwright GraphQL (AF/KL)."""
    from .air_france_klm.crawler import AirFranceKlmCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AirFranceKlmCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-turkish")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_turkish(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Turkish Airlines flight availability (TK)."""
    from .turkish_airlines.crawler import TurkishAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = TurkishAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-eva-air")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_eva_air(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: EVA Air daily lowest fares via getBestPrices (~300 days)."""
    from .eva_air.crawler import EvaAirCrawler

    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = EvaAirCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-lot")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_lot(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: LOT Polish Airlines price boxes (LO)."""
    from .lot_polish.crawler import LotPolishCrawler

    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = LotPolishCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-air-nz")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_air_nz(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Air New Zealand daily lowest fares via Sputnik (~300 days)."""
    from .air_nz.crawler import AirNzCrawler

    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AirNzCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-ethiopian")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_ethiopian(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Ethiopian Airlines daily fares via EveryMundo Sputnik (ET)."""
    from .ethiopian_airlines.crawler import EthiopianAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = EthiopianAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-cathay")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_cathay(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Cathay Pacific flight timetable + fare calendar (CX)."""
    from .cathay_pacific.crawler import CathayPacificCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = CathayPacificCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-malaysia")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_malaysia(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Malaysia Airlines low-fare calendar via AEM endpoint (MH)."""
    from .malaysia_airlines.crawler import MalaysiaAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = MalaysiaAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-vietnam")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_vietnam(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Vietnam Airlines schedule + fare calendar via middleware API (VN)."""
    from .vietnam_airlines.crawler import VietnamAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = VietnamAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-philippine")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_philippine(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Philippine Airlines flight schedule via flight status API (PR)."""
    from .philippine_airlines.crawler import PhilippineAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = PhilippineAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-hainan")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_hainan(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Hainan Airlines fare-trends calendar (HU, domestic CN only)."""
    from .hainan_airlines.crawler import HainanAirlinesCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = HainanAirlinesCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-amadeus")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_amadeus(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Amadeus GDS flight offers search (~400 airlines)."""
    from .amadeus_gds.crawler import AmadeusCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.GDS)

    async def _run():  # type: ignore[return]
        crawler = AmadeusCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def crawl_all(
    origin: str, destination: str, departure_date: str, cabin: str, json_output: bool
) -> None:
    """L1+L2 parallel crawl with merge."""
    from .google.crawler import GoogleFlightsCrawler
    from .kiwi.crawler import KiwiCrawler
    from .pipeline.merger import merge_results

    search_req = _build_search_request(origin, destination, departure_date, cabin)

    async def _run():  # type: ignore[return]
        l1_task = CrawlTask(
            search_request=search_req, source=DataSource.GOOGLE_PROTOBUF
        )
        l2_task = CrawlTask(search_request=search_req, source=DataSource.KIWI_API)

        google = GoogleFlightsCrawler()
        kiwi = KiwiCrawler()

        try:
            results = await asyncio.gather(
                google.crawl(l1_task),
                kiwi.crawl(l2_task),
                return_exceptions=True,
            )
        finally:
            await google.close()
            await kiwi.close()

        crawl_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.error("Crawl error: %s", r)
            else:
                crawl_results.append(r)

        return merge_results(crawl_results)

    merged = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps([f.model_dump(mode="json") for f in merged], indent=2))
    else:
        _print_results(merged)


@cli.command("crawl-jal")
@click.argument("origin")
@click.argument("destination")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_jal(
    origin: str,
    destination: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L2: Japan Airlines daily lowest fares via Sputnik (JL)."""
    from .jal.crawler import JalCrawler

    search_req = _build_search_request(
        origin,
        destination,
        "2026-03-01",
        cabin,
    )
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = JalCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-ana")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_ana(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L3: ANA flight search via Playwright (NH)."""
    from .ana.crawler import AnaCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = AnaCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-thai")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_thai(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L3: Thai Airways flight search via Playwright (TG)."""
    from .thai_airways.crawler import ThaiAirwaysCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = ThaiAirwaysCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("crawl-qatar")
@click.argument("origin")
@click.argument("destination")
@click.argument("departure_date")
@click.option("--cabin", default="ECONOMY", help="Cabin class")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.option("--store", is_flag=True, help="Store results to database")
def crawl_qatar(
    origin: str,
    destination: str,
    departure_date: str,
    cabin: str,
    json_output: bool,
    store: bool,
) -> None:
    """L3: Qatar Airways flight search via Playwright (QR)."""
    from .qatar_airways.crawler import QatarAirwaysCrawler

    search_req = _build_search_request(origin, destination, departure_date, cabin)
    task = CrawlTask(search_request=search_req, source=DataSource.DIRECT_CRAWL)

    async def _run():  # type: ignore[return]
        crawler = QatarAirwaysCrawler()
        try:
            return await crawler.crawl(task)
        finally:
            await crawler.close()

    result = asyncio.run(_run())
    if json_output:
        click.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    else:
        click.echo(f"Source: {result.source.value} | Duration: {result.duration_ms}ms")
        if result.error:
            click.echo(f"Error: {result.error}", err=True)
        _print_results(result.flights)

    if store and result.flights:
        _store_to_db(result.flights)


@cli.command("health")
def health_check() -> None:
    """Check health of all crawl sources."""
    from .air_busan.crawler import AirBusanCrawler
    from .air_france_klm.crawler import AirFranceKlmCrawler
    from .air_nz.crawler import AirNzCrawler
    from .air_premia.crawler import AirPremiaCrawler
    from .air_seoul.crawler import AirSeoulCrawler
    from .amadeus_gds.crawler import AmadeusCrawler
    from .ana.crawler import AnaCrawler
    from .cathay_pacific.crawler import CathayPacificCrawler
    from .eastar_jet.crawler import EastarJetCrawler
    from .ethiopian_airlines.crawler import EthiopianAirlinesCrawler
    from .eva_air.crawler import EvaAirCrawler
    from .google.crawler import GoogleFlightsCrawler
    from .hainan_airlines.crawler import HainanAirlinesCrawler
    from .jal.crawler import JalCrawler
    from .jeju_air.crawler import JejuAirCrawler
    from .jin_air.crawler import JinAirCrawler
    from .kiwi.crawler import KiwiCrawler
    from .lot_polish.crawler import LotPolishCrawler
    from .lufthansa_group.crawler import LufthansaCrawler
    from .malaysia_airlines.crawler import MalaysiaAirlinesCrawler
    from .philippine_airlines.crawler import PhilippineAirlinesCrawler
    from .qatar_airways.crawler import QatarAirwaysCrawler
    from .singapore_airlines.crawler import SingaporeAirlinesCrawler
    from .thai_airways.crawler import ThaiAirwaysCrawler
    from .turkish_airlines.crawler import TurkishAirlinesCrawler
    from .tway_air.crawler import TwayAirCrawler
    from .vietnam_airlines.crawler import VietnamAirlinesCrawler

    async def _run() -> dict[str, bool]:
        google = GoogleFlightsCrawler()
        kiwi = KiwiCrawler()
        jeju = JejuAirCrawler()
        eastar = EastarJetCrawler()
        premia = AirPremiaCrawler()
        amadeus = AmadeusCrawler()
        air_seoul = AirSeoulCrawler()
        jin_air = JinAirCrawler()
        tway = TwayAirCrawler()
        air_busan = AirBusanCrawler()
        lufthansa = LufthansaCrawler()
        singapore = SingaporeAirlinesCrawler()
        afklm = AirFranceKlmCrawler()
        turkish = TurkishAirlinesCrawler()
        eva_air = EvaAirCrawler()
        lot_polish = LotPolishCrawler()
        air_nz = AirNzCrawler()
        vietnam = VietnamAirlinesCrawler()
        philippine = PhilippineAirlinesCrawler()
        hainan = HainanAirlinesCrawler()
        ethiopian = EthiopianAirlinesCrawler()
        cathay = CathayPacificCrawler()
        malaysia = MalaysiaAirlinesCrawler()
        jal = JalCrawler()
        ana = AnaCrawler()
        thai = ThaiAirwaysCrawler()
        qatar = QatarAirwaysCrawler()
        try:
            results = await asyncio.gather(
                google.health_check(),
                kiwi.health_check(),
                jeju.health_check(),
                eastar.health_check(),
                premia.health_check(),
                amadeus.health_check(),
                air_seoul.health_check(),
                jin_air.health_check(),
                tway.health_check(),
                air_busan.health_check(),
                lufthansa.health_check(),
                singapore.health_check(),
                afklm.health_check(),
                turkish.health_check(),
                eva_air.health_check(),
                lot_polish.health_check(),
                air_nz.health_check(),
                vietnam.health_check(),
                philippine.health_check(),
                hainan.health_check(),
                ethiopian.health_check(),
                cathay.health_check(),
                malaysia.health_check(),
                jal.health_check(),
                ana.health_check(),
                thai.health_check(),
                qatar.health_check(),
                return_exceptions=True,
            )
        finally:
            await google.close()
            await kiwi.close()
            await jeju.close()
            await eastar.close()
            await premia.close()
            await amadeus.close()
            await air_seoul.close()
            await jin_air.close()
            await tway.close()
            await air_busan.close()
            await lufthansa.close()
            await singapore.close()
            await afklm.close()
            await turkish.close()
            await eva_air.close()
            await lot_polish.close()
            await air_nz.close()
            await vietnam.close()
            await philippine.close()
            await hainan.close()
            await ethiopian.close()
            await cathay.close()
            await malaysia.close()
            await jal.close()
            await ana.close()
            await thai.close()
            await qatar.close()

        return {
            "L1 (Google Protobuf)": not isinstance(results[0], Exception)
            and results[0],
            "L2 (Kiwi API)": not isinstance(results[1], Exception) and results[1],
            "L2 (Jeju Air)": not isinstance(results[2], Exception) and results[2],
            "L2 (Eastar Jet)": not isinstance(results[3], Exception) and results[3],
            "L3 (Air Premia)": not isinstance(results[4], Exception) and results[4],
            "L2 (Amadeus GDS)": not isinstance(results[5], Exception) and results[5],
            "L2 (Air Seoul)": not isinstance(results[6], Exception) and results[6],
            "L2 (Jin Air)": not isinstance(results[7], Exception) and results[7],
            "L2 (T'way Air)": not isinstance(results[8], Exception) and results[8],
            "L2 (Air Busan)": not isinstance(results[9], Exception) and results[9],
            "L2 (Lufthansa Group)": not isinstance(results[10], Exception)
            and results[10],
            "L2 (Singapore Airlines)": not isinstance(results[11], Exception)
            and results[11],
            "L3 (Air France-KLM)": not isinstance(results[12], Exception)
            and results[12],
            "L2 (Turkish Airlines)": not isinstance(results[13], Exception)
            and results[13],
            "L2 (EVA Air)": not isinstance(results[14], Exception) and results[14],
            "L2 (LOT Polish)": not isinstance(results[15], Exception) and results[15],
            "L2 (Air New Zealand)": not isinstance(results[16], Exception)
            and results[16],
            "L2 (Vietnam Airlines)": not isinstance(results[17], Exception)
            and results[17],
            "L2 (Philippine Airlines)": not isinstance(results[18], Exception)
            and results[18],
            "L2 (Hainan Airlines)": not isinstance(results[19], Exception)
            and results[19],
            "L2 (Ethiopian Airlines)": not isinstance(results[20], Exception)
            and results[20],
            "L2 (Cathay Pacific)": not isinstance(results[21], Exception)
            and results[21],
            "L2 (Malaysia Airlines)": not isinstance(results[22], Exception)
            and results[22],
            "L2 (JAL)": not isinstance(results[23], Exception) and results[23],
            "L3 (ANA)": not isinstance(results[24], Exception) and results[24],
            "L3 (Thai Airways)": not isinstance(results[25], Exception) and results[25],
            "L3 (Qatar Airways)": not isinstance(results[26], Exception)
            and results[26],
        }

    statuses = asyncio.run(_run())
    for source, ok in statuses.items():
        status = "OK" if ok else "FAIL"
        click.echo(f"  {source}: {status}")

    if not all(statuses.values()):
        sys.exit(1)


if __name__ == "__main__":
    cli()
