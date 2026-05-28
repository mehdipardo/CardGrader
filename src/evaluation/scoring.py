"""Scoring engine that combines condition and pricing into a final valuation."""

from src.models.card import CardCondition, CardPricing, CardReport, CardIdentity


# Mapping from overall_score ranges to the closest PSA-equivalent grade tier.
# Keys are (min_inclusive, max_exclusive) tuples, values are grade integers.
SCORE_TO_GRADE_TIER: dict[tuple[float, float], int] = {
    (9.5, 10.1): 10,
    (8.5, 9.5): 9,
    (7.0, 8.5): 7,
    (5.0, 7.0): 5,
    (3.0, 5.0): 3,
    (0.0, 3.0): 1,
}


class ScoringEngine:
    """Calculates the estimated market value of a card given its condition.

    Combines the CardCondition overall_score with the CardPricing grade tiers
    to produce a single estimated_value and a low/high value range that
    accounts for grading uncertainty.
    """

    def compute_report(
        self,
        identity: CardIdentity,
        condition: CardCondition,
        pricing: CardPricing,
    ) -> CardReport:
        """Produce a full CardReport from identity, condition, and pricing.

        Determines the nearest PSA grade tier from the overall_score, looks up
        the corresponding price, applies an uncertainty band, and assembles the
        final report.

        Args:
            identity: The identified card.
            condition: The assessed physical condition.
            pricing: Market pricing data for this card.

        Returns:
            A CardReport with estimated_value and value_range filled in.
        """
        raise NotImplementedError

    def map_score_to_grade_tier(self, overall_score: float) -> int:
        """Map a 1–10 overall condition score to the nearest PSA grade tier.

        Uses SCORE_TO_GRADE_TIER to find the matching bucket.

        Args:
            overall_score: Composite condition score (1.0–10.0).

        Returns:
            The closest PSA-style grade integer (1, 3, 5, 7, 9, or 10).
        """
        raise NotImplementedError

    def get_price_for_tier(self, pricing: CardPricing, grade_tier: int) -> float:
        """Retrieve the market price for a specific grade tier.

        Falls back to the raw_price if the requested tier has no data.

        Args:
            pricing: The pricing data object.
            grade_tier: PSA-style grade integer (1, 3, 5, 7, 9, or 10).

        Returns:
            The price for the given tier, or raw_price as fallback.
        """
        raise NotImplementedError

    def compute_value_range(
        self,
        estimated_value: float,
        condition: CardCondition,
    ) -> tuple[float, float]:
        """Compute a low/high value range based on grading uncertainty.

        Uses condition.confidence to widen or narrow the band: lower confidence
        produces a wider range. The band is expressed as a percentage of the
        estimated_value.

        Args:
            estimated_value: The point-estimate card value.
            condition: The condition assessment (confidence used for band width).

        Returns:
            Tuple of (value_range_low, value_range_high).
        """
        raise NotImplementedError

    def compute_confidence_score(
        self,
        id_confidence: float,
        condition_confidence: float,
    ) -> float:
        """Compute overall pipeline confidence from component confidences.

        Args:
            id_confidence: Confidence from the identification step (0.0–1.0).
            condition_confidence: Confidence from the grading step (0.0–1.0).

        Returns:
            Aggregate confidence score (0.0–1.0).
        """
        raise NotImplementedError
