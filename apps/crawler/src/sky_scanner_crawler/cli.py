"""CLI for standalone crawler testing."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import date

import click

from sky_scanner_core.schemas import (
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
def crawl_l1(
    origin: str, destination: str, departure_date: str, cabin: str, json_output: bool
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
    from .google.crawler import GoogleFlightsCrawler
    from .kiwi.crawler import KiwiCrawler

    async def _run() -> dict[str, bool]:
        google = GoogleFlightsCrawler()
        kiwi = KiwiCrawler()
        try:
            results = await asyncio.gather(
                google.health_check(),
                kiwi.health_check(),
                return_exceptions=True,
            )
        finally:
            await google.close()
            await kiwi.close()

        return {
            "L1 (Google Protobuf)": not isinstance(results[0], Exception)
            and results[0],
            "L2 (Kiwi API)": not isinstance(results[1], Exception) and results[1],
        }

    statuses = asyncio.run(_run())
    for source, ok in statuses.items():
        status = "OK" if ok else "FAIL"
        click.echo(f"  {source}: {status}")

    if not all(statuses.values()):
        sys.exit(1)


if __name__ == "__main__":
    cli()
