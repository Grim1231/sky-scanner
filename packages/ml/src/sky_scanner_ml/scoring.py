"""Flight scoring engine with weighted multi-factor evaluation."""

from __future__ import annotations

from datetime import datetime, time  # noqa: TC003
from typing import Any

from pydantic import BaseModel

from sky_scanner_ml.preference_filter import PostFilterConfig  # noqa: TC001

WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "PRICE": {
        "price": 0.50,
        "time": 0.20,
        "comfort": 0.10,
        "service": 0.10,
        "reliability": 0.10,
    },
    "TIME": {
        "price": 0.15,
        "time": 0.45,
        "comfort": 0.10,
        "service": 0.10,
        "reliability": 0.20,
    },
    "COMFORT": {
        "price": 0.15,
        "time": 0.10,
        "comfort": 0.45,
        "service": 0.20,
        "reliability": 0.10,
    },
    "BALANCED": {
        "price": 0.30,
        "time": 0.25,
        "comfort": 0.20,
        "service": 0.10,
        "reliability": 0.15,
    },
}


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a single flight."""

    price_score: float
    time_score: float
    comfort_score: float
    service_score: float
    reliability_score: float
    total_score: float
    priority: str


class FlightScorer:
    """Scores flights based on user preferences and weight profiles."""

    def __init__(self, config: PostFilterConfig) -> None:
        self._config = config
        self._weights = WEIGHT_PROFILES.get(
            config.priority, WEIGHT_PROFILES["BALANCED"]
        )

    def score_flights(
        self,
        flights: list[dict[str, Any]],
        seat_specs: dict[str, dict[str, Any]] | None = None,
    ) -> list[ScoreBreakdown]:
        """Score a list of flight dicts and return score breakdowns."""
        if not flights:
            return []

        prices = [f["lowest_price"] for f in flights]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price

        results: list[ScoreBreakdown] = []
        for flight in flights:
            price_score = self._score_price(
                flight["lowest_price"], min_price, price_range
            )
            time_score = self._score_time(flight["departure_time"])
            comfort_score = self._score_comfort(
                flight.get("airline_code", ""),
                flight.get("cabin_class", "ECONOMY"),
                seat_specs,
            )
            service_score = self._score_service(flight.get("prices", []))
            reliability_score = self._score_reliability(
                flight.get("airline_type", "LCC"),
                flight.get("source", ""),
            )

            total = (
                self._weights["price"] * price_score
                + self._weights["time"] * time_score
                + self._weights["comfort"] * comfort_score
                + self._weights["service"] * service_score
                + self._weights["reliability"] * reliability_score
            )

            results.append(
                ScoreBreakdown(
                    price_score=round(price_score, 4),
                    time_score=round(time_score, 4),
                    comfort_score=round(comfort_score, 4),
                    service_score=round(service_score, 4),
                    reliability_score=round(reliability_score, 4),
                    total_score=round(total, 4),
                    priority=self._config.priority,
                )
            )

        return results

    @staticmethod
    def _score_price(price: float, min_price: float, price_range: float) -> float:
        """Min-max normalization: cheapest=1.0, most expensive=0.0."""
        if price_range == 0:
            return 1.0
        return 1.0 - (price - min_price) / price_range

    def _score_time(self, departure_time: datetime) -> float:
        """Score based on proximity to preferred departure window."""
        start = self._config.departure_time_start
        end = self._config.departure_time_end
        if start is None or end is None:
            return 0.5

        dep_time = departure_time.time()
        if _time_in_range(start, end, dep_time):
            return 1.0

        hours_away = _hours_from_range(start, end, dep_time)
        max_decay_hours = 6.0
        return max(0.0, 1.0 - hours_away / max_decay_hours)

    def _score_comfort(
        self,
        airline_code: str,
        cabin_class: str,
        seat_specs: dict[str, dict[str, Any]] | None,
    ) -> float:
        """Score based on seat specifications vs preferences."""
        if seat_specs is None:
            return 0.5

        key = f"{airline_code}_{cabin_class}"
        spec = seat_specs.get(key)
        if spec is None:
            return 0.5

        scores: list[float] = []
        if self._config.min_seat_pitch is not None and spec.get("seat_pitch_inches"):
            ratio = spec["seat_pitch_inches"] / self._config.min_seat_pitch
            scores.append(min(ratio, 1.0))
        if self._config.min_seat_width is not None and spec.get("seat_width_inches"):
            ratio = spec["seat_width_inches"] / self._config.min_seat_width
            scores.append(min(ratio, 1.0))

        if not scores:
            return 0.5
        return sum(scores) / len(scores)

    def _score_service(self, prices: list[dict[str, Any]]) -> float:
        """Score based on baggage and meal inclusion."""
        if not self._config.baggage_required and not self._config.meal_required:
            return 1.0

        score = 0.0
        has_baggage = (
            any(p.get("includes_baggage") for p in prices) if prices else False
        )
        has_meal = any(p.get("includes_meal") for p in prices) if prices else False

        if self._config.baggage_required:
            score += 0.5 if has_baggage else 0.0
        else:
            score += 0.5

        if self._config.meal_required:
            score += 0.5 if has_meal else 0.0
        else:
            score += 0.5

        return score

    @staticmethod
    def _score_reliability(airline_type: str, source: str) -> float:
        """Score based on airline type and data source diversity."""
        base_scores = {"FSC": 0.8, "LCC": 0.5, "ULCC": 0.3}
        score = base_scores.get(airline_type, 0.5)
        # Multiple data sources indicator: source field contains comma-separated values
        if source and "," in source:
            score = min(score + 0.2, 1.0)
        return score


def _time_in_range(start: time, end: time, t: time) -> bool:
    """Check if time t falls within [start, end], handling overnight ranges."""
    if start <= end:
        return start <= t <= end
    # Overnight range (e.g., 22:00 - 06:00)
    return t >= start or t <= end


def _hours_from_range(start: time, end: time, t: time) -> float:
    """Calculate minimum hours from time t to the nearest edge of [start, end]."""
    t_mins = t.hour * 60 + t.minute
    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute

    if start_mins <= end_mins:
        dist = start_mins - t_mins if t_mins < start_mins else t_mins - end_mins
    else:
        # Overnight range
        if t_mins > end_mins and t_mins < start_mins:
            dist = min(t_mins - end_mins, start_mins - t_mins)
        else:
            dist = 0

    return dist / 60.0
