"""Heuristic price prediction and buy/wait recommendations."""

from __future__ import annotations

import statistics
from enum import StrEnum

from pydantic import BaseModel


class BuyRecommendation(StrEnum):
    """Recommendation for whether to buy now or wait."""

    BUY_NOW = "BUY_NOW"
    WAIT = "WAIT"
    NEUTRAL = "NEUTRAL"


class PricePrediction(BaseModel):
    """Price prediction result with recommendation."""

    current_avg_price: float
    predicted_direction: str  # UP, DOWN, STABLE
    confidence: float
    recommendation: BuyRecommendation
    reason: str
    best_price_seen: float
    worst_price_seen: float
    percentile_current: float
    days_until_departure: int


class BestTimeResult(BaseModel):
    """Result for best time to buy analysis."""

    optimal_days_before: int
    estimated_price_at_optimal: float | None
    confidence: float
    current_days_before: int
    recommendation: str


class HeuristicPredictor:
    """Heuristic-based flight price predictor.

    Uses historical price data to provide buy/wait recommendations
    based on simple statistical analysis.
    """

    def __init__(self, prices: list[float], days_until_departure: int) -> None:
        self._prices = prices
        self._days_until_departure = days_until_departure

    def _confidence(self) -> float:
        n = len(self._prices)
        if n < 5:
            return 0.3
        if n <= 20:
            return 0.6
        return 0.8

    def _percentile(self, value: float) -> float:
        """Calculate the percentile of a value within the price list."""
        if not self._prices:
            return 50.0
        below = sum(1 for p in self._prices if p < value)
        return (below / len(self._prices)) * 100

    def _direction(self) -> str:
        """Predict price direction based on moving averages."""
        if len(self._prices) < 7:
            return "STABLE"

        recent_7 = self._prices[-7:]
        ma_7 = statistics.mean(recent_7)

        if len(self._prices) >= 30:
            ma_30 = statistics.mean(self._prices[-30:])
        else:
            ma_30 = statistics.mean(self._prices)

        diff_pct = (ma_7 - ma_30) / ma_30 * 100 if ma_30 else 0

        if diff_pct > 3:
            return "UP"
        if diff_pct < -3:
            return "DOWN"
        return "STABLE"

    def predict(self) -> PricePrediction:
        """Generate a price prediction and buy recommendation."""
        if not self._prices:
            return PricePrediction(
                current_avg_price=0,
                predicted_direction="STABLE",
                confidence=0.3,
                recommendation=BuyRecommendation.NEUTRAL,
                reason="No price data available.",
                best_price_seen=0,
                worst_price_seen=0,
                percentile_current=50.0,
                days_until_departure=self._days_until_departure,
            )

        recent = self._prices[-7:] if len(self._prices) >= 7 else self._prices
        current_avg = statistics.mean(recent)
        best = min(self._prices)
        worst = max(self._prices)
        percentile = self._percentile(current_avg)
        direction = self._direction()
        confidence = self._confidence()

        # Scoring logic
        if self._days_until_departure < 7:
            recommendation = BuyRecommendation.BUY_NOW
            reason = (
                "Departure is less than 7 days away; "
                "prices typically rise closer to departure."
            )
        elif percentile < 25:
            recommendation = BuyRecommendation.BUY_NOW
            reason = (
                f"Current price is in the {percentile:.0f}th percentile"
                " — lower than 75% of observed prices."
            )
        elif percentile > 75 and self._days_until_departure > 14:
            recommendation = BuyRecommendation.WAIT
            reason = (
                f"Current price is in the {percentile:.0f}th percentile and there are "
                f"{self._days_until_departure} days until departure. Prices may drop."
            )
        else:
            recommendation = BuyRecommendation.NEUTRAL
            reason = "Price is in the normal range. No strong signal to buy or wait."

        return PricePrediction(
            current_avg_price=round(current_avg, 2),
            predicted_direction=direction,
            confidence=confidence,
            recommendation=recommendation,
            reason=reason,
            best_price_seen=best,
            worst_price_seen=worst,
            percentile_current=round(percentile, 1),
            days_until_departure=self._days_until_departure,
        )

    def best_time(self) -> BestTimeResult:
        """Analyze the best time to buy based on historical patterns."""
        confidence = self._confidence()

        # Heuristic: domestic flights optimal ~21 days, international ~45 days
        optimal_days = 21 if len(self._prices) < 30 else 45

        estimated_price: float | None = None
        if len(self._prices) >= 5:
            # Estimate based on the lowest quartile of observed prices
            sorted_prices = sorted(self._prices)
            q1_idx = max(0, len(sorted_prices) // 4)
            estimated_price = round(sorted_prices[q1_idx], 2)

        if self._days_until_departure <= 7:
            rec = "Buy now — departure is imminent."
        elif self._days_until_departure < optimal_days:
            rec = "Consider buying soon — approaching optimal window."
        else:
            rec = (
                f"Optimal purchase window is around "
                f"{optimal_days} days before departure."
            )

        return BestTimeResult(
            optimal_days_before=optimal_days,
            estimated_price_at_optimal=estimated_price,
            confidence=confidence,
            current_days_before=self._days_until_departure,
            recommendation=rec,
        )
