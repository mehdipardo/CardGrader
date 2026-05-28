"""Vision-based physical condition grader for Pokémon TCG cards."""

from pathlib import Path
from typing import Optional

from src.models.card import CardCondition

CENTERING_CONFIDENCE_PENALTY = 0.15


class CardGrader:
    """Uses Claude's vision capabilities to assess the physical condition of a card.

    Analyses card images across four grading dimensions — centering, corners,
    edges, and surface — and returns a CardCondition with sub-scores and an
    overall composite grade on a 1–10 scale.

    Centering is ideally evaluated from the back (verso) which shows the border
    symmetry most clearly. When only the front is available, centering is still
    estimated but confidence is reduced by CENTERING_CONFIDENCE_PENALTY (0.15).
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the grader with an Anthropic API key.

        Args:
            api_key: Anthropic API key for vision requests.
        """
        self.api_key = api_key
        self._client = None  # Anthropic client, initialised on first use

    def grade(
        self,
        front_image_path: str,
        back_image_path: Optional[str] = None,
    ) -> CardCondition:
        """Assess the physical condition of a card from its image(s).

        Sends image(s) to Claude with a grading rubric prompt. Corners, edges,
        and surface are evaluated from the front. Centering is evaluated from
        the back when available; when only the front is provided, centering is
        estimated from the front and the overall confidence is reduced by
        CENTERING_CONFIDENCE_PENALTY (0.15).

        Args:
            front_image_path: Path to the front (recto) card image.
            back_image_path: Optional path to the back (verso) card image.
                When provided, enables accurate centering measurement from
                border symmetry on the reverse side.

        Returns:
            A CardCondition with scores for each dimension plus the overall
            composite grade and model confidence.

        Raises:
            FileNotFoundError: If front_image_path (or back_image_path when
                provided) does not exist.
        """
        raise NotImplementedError

    def _build_grading_prompt(self) -> str:
        """Return the system + user prompt used to instruct the grading model.

        The prompt defines a strict rubric for each sub-score and instructs
        the model to return a JSON object with the four dimension scores and
        its confidence level.

        Returns:
            The complete prompt string.
        """
        raise NotImplementedError

    def _parse_condition_response(self, raw_response: str) -> CardCondition:
        """Parse the model's grading response into a CardCondition.

        Args:
            raw_response: Raw text response from Claude containing the scores.

        Returns:
            A populated CardCondition.

        Raises:
            ValueError: If required score fields are missing or out of range.
        """
        raise NotImplementedError

    def _compute_overall_score(
        self,
        centering: float,
        corners: float,
        edges: float,
        surface: float,
    ) -> float:
        """Compute the weighted composite overall grade.

        Default weights: corners 30 %, edges 25 %, surface 30 %, centering 15 %.
        Weights are intentionally close to PSA's known emphasis areas.

        Args:
            centering: Centering sub-score (1–10).
            corners: Corners sub-score (1–10).
            edges: Edges sub-score (1–10).
            surface: Surface sub-score (1–10).

        Returns:
            Weighted composite score rounded to one decimal place.
        """
        raise NotImplementedError
