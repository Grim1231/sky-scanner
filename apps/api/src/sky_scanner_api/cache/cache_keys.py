"""Cache key builders for consistent namespacing."""

from __future__ import annotations

import hashlib


def search_key(origin: str, dest: str, date: str, cabin: str) -> str:
    """Build cache key for flight search results."""
    return f"search:{origin}:{dest}:{date}:{cabin}"


def price_history_key(origin: str, dest: str, start: str, end: str) -> str:
    """Build cache key for price history."""
    return f"prices:{origin}:{dest}:{start}:{end}"


def airport_search_key(query: str) -> str:
    """Build cache key for airport autocomplete."""
    return f"airports:search:{query}"


def airlines_list_key(type_filter: str | None, alliance_filter: str | None) -> str:
    """Build cache key for airline listings."""
    return f"airlines:list:{type_filter}:{alliance_filter}"


def nl_search_key(query: str) -> str:
    """Build cache key for natural language search."""
    digest = hashlib.md5(query.encode()).hexdigest()
    return f"nl_search:{digest}"


def prediction_key(origin: str, dest: str, date: str) -> str:
    """Build cache key for price prediction."""
    return f"prediction:{origin}:{dest}:{date}"


def best_time_key(origin: str, dest: str) -> str:
    """Build cache key for best-time analysis."""
    return f"best_time:{origin}:{dest}"
