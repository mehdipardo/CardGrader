"""Orchestrator for the end-to-end Pokémon TCG card grading pipeline."""

import os
from pathlib import Path
from typing import Union

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

    def evaluate(self, image_path: Union[str, Path]) -> CardReport:
        """Run the full grading pipeline on a single card image.

        Executes each pipeline step in sequence and returns the final report.

        Args:
            image_path: Path to the card photo (JPEG, PNG, or WEBP).

        Returns:
            A CardReport with identity, condition, pricing, and valuation.

        Raises:
            FileNotFoundError: If image_path does not exist.
            LookupError: If the card cannot be found in the TCG database.
            ValueError: If any step produces an unusable result.
        """
        raise NotImplementedError

    def evaluate_batch(self, image_paths: list[Union[str, Path]]) -> list[CardReport]:
        """Run the grading pipeline on multiple card images.

        Processes each image independently. Errors on individual cards are
        caught and logged without aborting the rest of the batch.

        Args:
            image_paths: List of paths to card images.

        Returns:
            List of CardReport objects, one per successfully processed image.
        """
        raise NotImplementedError
