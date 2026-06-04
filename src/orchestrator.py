"""Orchestrator for the end-to-end Pokémon TCG card grading pipeline."""

import json
import os
import sys
from typing import Optional

from src.agents.identifier import CardIdentifierAgent
from src.evaluation.grader import CardGrader
from src.evaluation.scoring import ScoringEngine
from src.models.card import CardReport
from src.tools.card_lookup import CardLookupTool
from src.tools.pricing import PricingTool


class CardGraderOrchestrator:
    """Coordinates all agents and tools to produce a CardReport from a card photo.

    Pipeline:
      1. Identify  — Claude Vision reads the front image → CardIdentity
      2. Resolve   — TCGDex card_lookup enriches identity → full card dict + baseline prices
      3. Grade     — Claude Vision evaluates physical condition → CardCondition
      4. Price     — PricingTool extracts CardPricing from TCGDex data (+ RapidAPI if available)
      5. Score     — ScoringEngine maps condition → PSA tier → estimated value → CardReport
    """

    def __init__(
        self,
        anthropic_api_key: str,
        rapidapi_key: Optional[str] = None,
    ) -> None:
        """Initialise all agents and tools.

        Args:
            anthropic_api_key: Key for Claude vision calls (identifier + grader).
            rapidapi_key: Optional RapidAPI key for language-specific CardMarket
                prices and PSA graded data. System works without it (TCGDex only).
        """
        self.identifier = CardIdentifierAgent(api_key=anthropic_api_key)
        self.lookup     = CardLookupTool()
        self.grader     = CardGrader(api_key=anthropic_api_key)
        self.pricing    = PricingTool(rapidapi_key=rapidapi_key)
        self.scorer     = ScoringEngine()

    @classmethod
    def from_env(cls) -> "CardGraderOrchestrator":
        """Instantiate the orchestrator using environment variables.

        Required: ANTHROPIC_API_KEY
        Optional: RAPIDAPI_KEY (enables language-specific prices and PSA grades)

        Raises:
            KeyError: If ANTHROPIC_API_KEY is not set.
        """
        return cls(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            rapidapi_key=os.environ.get("RAPIDAPI_KEY"),
        )

    def evaluate(
        self,
        front_image_path: str,
        back_image_path: Optional[str] = None,
    ) -> CardReport:
        """Run the full grading pipeline on a card.

        Args:
            front_image_path: Path to the front (recto) card image.
            back_image_path: Optional path to the back (verso) card image.
                When provided, enables accurate centering measurement.

        Returns:
            A fully populated CardReport.

        Raises:
            FileNotFoundError: If an image path does not exist.
            CardNotFoundError: If the card cannot be found in TCGDex.
            ValueError: If any step produces an unusable result.
        """
        # Step 1 — Identify
        identity = self.identifier.identify(front_image_path=front_image_path)

        # Step 2 — Resolve (TCGDex)
        tcgdex_card = self.lookup.resolve(identity)

        # Enrich identity with TCGDex metadata
        identity.set_name  = identity.set_name  or (tcgdex_card.get("set") or {}).get("name", "")
        identity.set_code  = identity.set_code   or tcgdex_card.get("id", "").split("-")[0] or None
        identity.rarity    = identity.rarity     or tcgdex_card.get("rarity")

        # Step 3 — Grade
        condition = self.grader.grade(
            front_image_path=front_image_path,
            back_image_path=back_image_path,
        )

        # Step 4 — Price
        pricing = self.pricing.fetch_prices(identity=identity, tcgdex_card=tcgdex_card)

        # Step 5 — Score
        report = self.scorer.compute_report(
            identity=identity,
            condition=condition,
            pricing=pricing,
            front_image_path=front_image_path,
            back_image_path=back_image_path,
        )

        return report

    def evaluate_batch(
        self,
        image_pairs: list[tuple[str, Optional[str]]],
    ) -> list[CardReport]:
        """Run the grading pipeline on multiple cards.

        Each entry is a (front_image_path, back_image_path) tuple.
        Errors on individual cards are caught and printed without aborting the batch.

        Args:
            image_pairs: List of (front_image_path, back_image_path) tuples.

        Returns:
            List of CardReport objects for successfully processed cards.
        """
        reports = []
        for i, (front, back) in enumerate(image_pairs):
            try:
                reports.append(self.evaluate(front, back))
            except Exception as exc:
                print(f"[batch] card {i+1} failed ({front}): {exc}", file=sys.stderr)
        return reports


if __name__ == "__main__":
    import argparse

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.orchestrator",
        description="Full CardGrader pipeline: identify → resolve → grade → price → score.",
    )
    parser.add_argument("--front", required=True, metavar="PATH",
                        help="Path to the front (recto) card image.")
    parser.add_argument("--back", default=None, metavar="PATH",
                        help="Path to the back (verso) card image (optional).")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in environment or .env file")
        sys.exit(1)

    orchestrator = CardGraderOrchestrator.from_env()

    try:
        report = orchestrator.evaluate(
            front_image_path=args.front,
            back_image_path=args.back,
        )
        print(json.dumps(
            {
                "identity": {
                    "name":     report.identity.name,
                    "number":   report.identity.number,
                    "language": report.identity.language,
                    "set_name": report.identity.set_name,
                    "set_code": report.identity.set_code,
                    "rarity":   report.identity.rarity,
                },
                "condition": {
                    "centering":    report.condition.centering,
                    "corners":      report.condition.corners,
                    "edges":        report.condition.edges,
                    "surface":      report.condition.surface,
                    "overall_score":report.condition.overall_score,
                    "confidence":   report.condition.confidence,
                },
                "pricing": {
                    "raw_price":         report.pricing.raw_price,
                    "currency":          report.pricing.currency,
                    "grade_10":          report.pricing.grade_10,
                    "grade_9":           report.pricing.grade_9,
                    "grade_7":           report.pricing.grade_7,
                    "grade_5":           report.pricing.grade_5,
                    "grade_3":           report.pricing.grade_3,
                    "cardmarket_trend":  report.pricing.cardmarket_trend,
                    "tcgplayer_market":  report.pricing.tcgplayer_market,
                    "source_detail":     report.pricing.source_detail,
                    "language_specific": report.pricing.language_specific,
                },
                "valuation": {
                    "estimated_value":  report.estimated_value,
                    "value_range_low":  report.value_range_low,
                    "value_range_high": report.value_range_high,
                    "confidence_score": report.confidence_score,
                },
            },
            indent=2,
            ensure_ascii=False,
        ))
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
