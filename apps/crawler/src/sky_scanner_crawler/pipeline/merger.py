"""Merge and deduplicate flight results from multiple crawl sources."""

from __future__ import annotations

import logging

from sky_scanner_core.schemas import CrawlResult, DataSource, NormalizedFlight

logger = logging.getLogger(__name__)

# Higher value = higher trust.  Used to pick the "canonical" metadata when
# the same flight appears from multiple sources.
_TRUST_ORDER: dict[DataSource, int] = {
    DataSource.GOOGLE_PROTOBUF: 40,
    DataSource.KIWI_API: 30,
    DataSource.DIRECT_CRAWL: 20,
    DataSource.GDS: 10,
}


def merge_results(results: list[CrawlResult]) -> list[NormalizedFlight]:
    """Merge flights from several :class:`CrawlResult` objects.

    * Groups flights by :pyattr:`NormalizedFlight.dedup_key`.
    * For duplicates, keeps the metadata from the highest-trust source and
      collects **all** prices into a single ``prices`` list.
    * Returns the merged list sorted by :pyattr:`lowest_price` ascending.
    """
    groups: dict[str, NormalizedFlight] = {}

    for cr in results:
        if not cr.success:
            continue
        for flight in cr.flights:
            key = flight.dedup_key
            existing = groups.get(key)
            if existing is None:
                groups[key] = flight.model_copy(deep=True)
            else:
                # Merge prices
                existing.prices.extend(flight.prices)
                # Keep metadata from the more trusted source
                if _TRUST_ORDER.get(flight.source, 0) > _TRUST_ORDER.get(
                    existing.source, 0
                ):
                    # Overwrite metadata fields while preserving merged prices
                    merged_prices = existing.prices
                    groups[key] = flight.model_copy(
                        deep=True, update={"prices": merged_prices}
                    )

    merged = list(groups.values())
    merged.sort(
        key=lambda f: f.lowest_price if f.lowest_price is not None else float("inf"),
    )

    logger.info(
        "Merged %d results into %d unique flights",
        sum(len(cr.flights) for cr in results),
        len(merged),
    )
    return merged
