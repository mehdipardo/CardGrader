"""Scoring engine that combines condition and pricing into a final valuation."""

from src.models.card import CardCondition, CardIdentity, CardPricing, CardReport

# Mapping from overall_score ranges to the closest PSA-equivalent grade tier.
# Keys are (min_inclusive, max_exclusive) tuples, values are grade integers.
SCORE_TO_GRADE_TIER: dict[tuple[float, float], int] = {
    (9.5, 10.1): 10,
    (8.5, 9.5):  9,
    (7.0, 8.5):  7,
    (5.0, 7.0):  5,
    (3.0, 5.0):  3,
    (0.0, 3.0):  1,
}

# Multipliers applied to raw_price when a graded price is not available.
# Reflects typical market premium/discount vs. raw for each PSA tier.
GRADE_MULTIPLIERS: dict[int, float] = {
    10: 6.0,
    9:  2.8,
    7:  1.6,
    5:  1.1,
    3:  0.75,
    1:  0.35,
}

TIER_TO_FIELD: dict[int, str] = {
    10: "grade_10",
    9:  "grade_9",
    7:  "grade_7",
    5:  "grade_5",
    3:  "grade_3",
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
        front_image_path: str = "",
        back_image_path: str | None = None,
    ) -> CardReport:
        """Produce a full CardReport from identity, condition, and pricing.

        Maps overall_score → PSA tier → price, applies uncertainty band,
        and computes an aggregate pipeline confidence score.

        Args:
            identity: The identified card.
            condition: The assessed physical condition.
            pricing: Market pricing data for this card.
            front_image_path: Path to the front image (stored in the report).
            back_image_path: Path to the back image, or None.

        Returns:
            A CardReport with all valuation fields populated.
        """
        grade_tier = self.map_score_to_grade_tier(condition.overall_score)
        estimated_value = self.get_price_for_tier(pricing, grade_tier)
        value_low, value_high = self.compute_value_range(estimated_value, condition)

        # Use grader confidence directly — identifier doesn't expose one yet
        confidence = round(condition.confidence, 4)

        return CardReport(
            identity=identity,
            condition=condition,
            pricing=pricing,
            estimated_value=round(estimated_value, 2),
            value_range_low=value_low,
            value_range_high=value_high,
            confidence_score=confidence,
            front_image_path=front_image_path,
            back_image_path=back_image_path,
        )

    def map_score_to_grade_tier(self, overall_score: float) -> int:
        """Map a 0–10 overall condition score to the nearest PSA grade tier.

        Args:
            overall_score: Composite condition score (0.0–10.0).

        Returns:
            PSA-style grade integer: 1, 3, 5, 7, 9, or 10.
        """
        for (low, high), tier in SCORE_TO_GRADE_TIER.items():
            if low <= overall_score < high:
                return tier
        return 1  # fallback for scores exactly at 0.0

    def get_price_for_tier(self, pricing: CardPricing, grade_tier: int) -> float:
        """Retrieve the market price for a specific grade tier.

        Uses the graded price if available; falls back to raw_price × a
        PSA-multiplier when graded data is absent.

        Args:
            pricing: The pricing data object.
            grade_tier: PSA-style grade integer (1, 3, 5, 7, 9, or 10).

        Returns:
            Estimated card value for the given tier.
        """
        field = TIER_TO_FIELD.get(grade_tier)
        if field:
            val = getattr(pricing, field, None)
            if val is not None:
                return float(val)
        # No graded price available — estimate from raw
        multiplier = GRADE_MULTIPLIERS.get(grade_tier, 1.0)
        return pricing.raw_price * multiplier

    def compute_value_range(
        self,
        estimated_value: float,
        condition: CardCondition,
    ) -> tuple[float, float]:
        """Compute a low/high value range based on grading uncertainty.

        Band width is inversely proportional to confidence:
          confidence=1.0 → ±10%, confidence=0.0 → ±50%.

        Args:
            estimated_value: The point-estimate card value.
            condition: Used for its confidence field.

        Returns:
            Tuple of (value_range_low, value_range_high), both rounded to 2dp.
        """
        band = 0.10 + (1.0 - condition.confidence) * 0.40
        low  = round(max(0.0, estimated_value * (1 - band)), 2)
        high = round(estimated_value * (1 + band), 2)
        return low, high

    def compute_confidence_score(
        self,
        id_confidence: float,
        condition_confidence: float,
    ) -> float:
        """Compute overall pipeline confidence as the geometric mean of components.

        Geometric mean penalises a weak link in either identification or grading.

        Args:
            id_confidence: Confidence from the identification step (0.0–1.0).
            condition_confidence: Confidence from the grading step (0.0–1.0).

        Returns:
            Aggregate confidence score (0.0–1.0).
        """
        return round((id_confidence * condition_confidence) ** 0.5, 4)
