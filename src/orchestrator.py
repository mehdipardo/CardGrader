"""Orchestrator for the end-to-end Pokémon TCG card grading pipeline."""

import os
from typing import Optional

from src.agents.identifier import CardIdentifierAgent
from src.evaluation.grader import CardGrader
from src.evaluation.scoring import ScoringEngine
from src.models.card import CardReport
from src.tools.card_lookup import CardLookupTool
from src.tools.pricing import PricingTool


class CardGraderOrchestrator:
    """Coordinates all agents and tools to produce a CardReport from an image.

    Pipeline steps:
      1. Identify the card via vision (CardIdentifierAgent).
      2. Enrich identity with official set code via TCG API (CardLookupTool).
      3. Assess physical condition via vision (CardGrader).
      4. Fetch current market prices (PricingTool).
      5. Compute final valuation (ScoringEngine).
    """

    def __init__(
        self,
        anthropic_api_key: str,
        pokemon_tcg_api_key: str,
    ) -> None:
        """Initialise all agents and tools.

        Args:
            anthropic_api_key: Key for Claude vision calls.
            pokemon_tcg_api_key: Key for TCG and pricing API calls.
        """
        self.identifier = CardIdentifierAgent(api_key=anthropic_api_key)
        self.lookup = CardLookupTool(api_key=pokemon_tcg_api_key)
        self.grader = CardGrader(api_key=anthropic_api_key)
        self.pricing = PricingTool(api_key=pokemon_tcg_api_key)
        self.scorer = ScoringEngine()

    @classmethod
    def from_env(cls) -> "CardGraderOrchestrator":
        """Instantiate the orchestrator using keys from environment variables.

        Reads ANTHROPIC_API_KEY and POKEMON_TCG_API_KEY from the environment.

        Returns:
            A fully configured CardGraderOrchestrator.

        Raises:
            KeyError: If either environment variable is not set.
        """
        return cls(
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            pokemon_tcg_api_key=os.environ["POKEMON_TCG_API_KEY"],
        )

    def evaluate(
        self,
        front_image_path: str,
        back_image_path: Optional[str] = None,
    ) -> CardReport:
        """Run the full grading pipeline on a card.

        Executes each pipeline step in sequence and returns the final report.
        Identification is performed on the front only. Grading uses both sides
        when the back is provided; otherwise centering confidence is penalised.

        Args:
            front_image_path: Path to the front (recto) card image.
            back_image_path: Optional path to the back (verso) card image.

        Returns:
            A CardReport with identity, condition, pricing, and valuation.

        Raises:
            FileNotFoundError: If front_image_path (or back_image_path when
                provided) does not exist.
            LookupError: If the card cannot be found in the TCG database.
            ValueError: If any step produces an unusable result.
        """
        raise NotImplementedError

    def evaluate_batch(
        self,
        image_pairs: list[tuple[str, Optional[str]]],
    ) -> list[CardReport]:
        """Run the grading pipeline on multiple cards.

        Each entry is a (front_image_path, back_image_path) tuple; pass None
        as the second element when no back image is available.
        Errors on individual cards are caught and logged without aborting the batch.

        Args:
            image_pairs: List of (front_image_path, back_image_path) tuples.

        Returns:
            List of CardReport objects, one per successfully processed card.
        """
        raise NotImplementedError
