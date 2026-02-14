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


@cli.command("health")
def health_check() -> None:
    """Check health of all crawl sources."""
    from .air_premia.crawler import AirPremiaCrawler
    from .air_seoul.crawler import AirSeoulCrawler
    from .amadeus_gds.crawler import AmadeusCrawler
    from .eastar_jet.crawler import EastarJetCrawler
    from .google.crawler import GoogleFlightsCrawler
    from .jeju_air.crawler import JejuAirCrawler
    from .jin_air.crawler import JinAirCrawler
    from .kiwi.crawler import KiwiCrawler

    async def _run() -> dict[str, bool]:
        google = GoogleFlightsCrawler()
        kiwi = KiwiCrawler()
        jeju = JejuAirCrawler()
        eastar = EastarJetCrawler()
        premia = AirPremiaCrawler()
        amadeus = AmadeusCrawler()
        air_seoul = AirSeoulCrawler()
        jin_air = JinAirCrawler()
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
        }

    statuses = asyncio.run(_run())
    for source, ok in statuses.items():
        status = "OK" if ok else "FAIL"
        click.echo(f"  {source}: {status}")

    if not all(statuses.values()):
        sys.exit(1)


if __name__ == "__main__":
    cli()
