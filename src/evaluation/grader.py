"""Vision-based physical condition grader for Pokémon TCG cards."""

import base64
import json
import sys
from pathlib import Path
from typing import Optional

import anthropic

from src.models.card import CardCondition

MODEL = "claude-sonnet-4-6"

CENTERING_CONFIDENCE_PENALTY = 0.15

# PSA-aligned weights for the composite score
WEIGHTS = {"corners": 0.30, "surface": 0.30, "edges": 0.25, "centering": 0.15}

MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

SYSTEM_PROMPT = """You are an expert Pokémon TCG card grader with the same standards as PSA/BGS.
Your task is to assess the physical condition of a card from its images.
You MUST respond with valid JSON only — no markdown, no explanation, no extra text.
Be precise and critical: do not round scores up out of generosity."""

def _build_user_prompt(has_back: bool) -> str:
    centering_instruction = (
        "CENTERING — measured from the BACK image (verso). "
        "Compare the border widths: top vs bottom, left vs right. "
        "10 = perfectly centred, 5 = clearly off-centre, 1 = severely miscentred."
        if has_back else
        "CENTERING — back image not provided, estimate from FRONT borders only. "
        "Note: accuracy is reduced without the back image."
    )
    return f"""Grade this Pokémon TCG card and return a JSON object with exactly this structure:

{{
  "centering": <0-10>,
  "corners": <0-10>,
  "edges": <0-10>,
  "surface": <0-10>,
  "details": {{
    "corners_observations": "<describe each of the 4 corners individually>",
    "edges_observations": "<describe each of the 4 edges individually>",
    "surface_observations": "<describe front and back surface separately>",
    "centering_observations": "<describe border ratios and any offset>"
  }},
  "confidence": <0.0-1.0>
}}

Grading rubric — score each criterion from 0 to 10:

1. CORNERS (weight 30%) — examine all 4 corners individually
   Look for: wear, bending, crushing, whitening/fraying
   10 = razor sharp, 8 = slight wear, 6 = moderate wear, 4 = heavy wear, 2 = severe damage

2. EDGES (weight 25%) — examine all 4 edges individually
   Look for: chipping (white specks), roughness, indentations, peeling
   10 = perfectly smooth, 8 = minor chipping, 6 = moderate chipping, 4 = heavy chipping, 2 = severe damage

3. SURFACE (weight 30%) — examine FRONT and BACK separately
   Look for: scratches, scuff marks, print lines, stains, loss of gloss/shine, dents
   10 = pristine, 8 = very light scratches, 6 = light scratches/scuffs, 4 = heavy scratches, 2 = severe damage

4. {centering_instruction}

Rules:
- Scores must be between 0.0 and 10.0 (one decimal allowed)
- Be critical and precise — do not inflate scores
- Return ONLY the JSON object, nothing else"""


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
        self._client: anthropic.Anthropic | None = None

    def _build_client(self) -> anthropic.Anthropic:
        """Lazily initialise and return the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def grade(
        self,
        front_image_path: str,
        back_image_path: Optional[str] = None,
    ) -> CardCondition:
        """Assess the physical condition of a card from its image(s).

        Corners, edges, and surface are evaluated from the front. Centering is
        evaluated from the back when available; when only the front is provided,
        centering is estimated from the front and confidence is reduced by
        CENTERING_CONFIDENCE_PENALTY (0.15).

        Args:
            front_image_path: Path to the front (recto) card image.
            back_image_path: Optional path to the back (verso) card image.

        Returns:
            A CardCondition with sub-scores, overall grade, and confidence.

        Raises:
            FileNotFoundError: If front_image_path (or back_image_path when
                provided) does not exist.
            ValueError: If the file format is unsupported or the response
                cannot be parsed.
            anthropic.APIError: On Anthropic API failures.
        """
        front = Path(front_image_path)
        if not front.exists():
            raise FileNotFoundError(f"Front image not found: {front}")

        content: list[dict] = []

        front_data, front_media = self._load_image_as_base64(front)
        content.append({"type": "text", "text": "FRONT IMAGE (recto):"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": front_media, "data": front_data},
        })

        if back_image_path is not None:
            back = Path(back_image_path)
            if not back.exists():
                raise FileNotFoundError(f"Back image not found: {back}")
            back_data, back_media = self._load_image_as_base64(back)
            content.append({"type": "text", "text": "BACK IMAGE (verso):"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": back_media, "data": back_data},
            })

        content.append({"type": "text", "text": _build_user_prompt(has_back=back_image_path is not None)})

        client = self._build_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        raw_text = message.content[0].text
        condition = self._parse_condition_response(raw_text)

        if back_image_path is None:
            condition.confidence = max(0.0, round(condition.confidence - CENTERING_CONFIDENCE_PENALTY, 4))

        return condition

    def _load_image_as_base64(self, image_path: Path) -> tuple[str, str]:
        """Read an image file and return (base64_data, media_type).

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64-encoded string, MIME type string).

        Raises:
            ValueError: If the file extension is not supported.
        """
        ext = image_path.suffix.lower()
        media_type = MEDIA_TYPES.get(ext)
        if media_type is None:
            raise ValueError(
                f"Unsupported image format '{ext}'. Supported: {list(MEDIA_TYPES)}"
            )
        return base64.standard_b64encode(image_path.read_bytes()).decode("utf-8"), media_type

    def _parse_condition_response(self, raw_response: str) -> CardCondition:
        """Parse the model's JSON grading response into a CardCondition.

        Args:
            raw_response: Raw text content from Claude.

        Returns:
            A populated CardCondition.

        Raises:
            ValueError: If the response is not valid JSON, required fields are
                missing, or scores are outside the 0–10 range.
        """
        text = raw_response.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip().rstrip("`").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model returned non-JSON response: {raw_response!r}"
            ) from exc

        required = ("centering", "corners", "edges", "surface", "confidence")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Required fields missing in grading response: {missing}")

        scores = {k: float(data[k]) for k in ("centering", "corners", "edges", "surface")}
        for field, value in scores.items():
            if not (0.0 <= value <= 10.0):
                raise ValueError(f"Score '{field}' out of range: {value}")

        overall = self._compute_overall_score(**scores)

        return CardCondition(
            centering=scores["centering"],
            corners=scores["corners"],
            edges=scores["edges"],
            surface=scores["surface"],
            overall_score=overall,
            confidence=max(0.0, min(1.0, float(data["confidence"]))),
        )

    def _compute_overall_score(
        self,
        centering: float,
        corners: float,
        edges: float,
        surface: float,
    ) -> float:
        """Compute the weighted composite overall grade.

        Weights (PSA-aligned): corners 30%, surface 30%, edges 25%, centering 15%.

        Args:
            centering: Centering sub-score (0–10).
            corners: Corners sub-score (0–10).
            edges: Edges sub-score (0–10).
            surface: Surface sub-score (0–10).

        Returns:
            Weighted composite score rounded to one decimal place.
        """
        score = (
            corners  * WEIGHTS["corners"]  +
            surface  * WEIGHTS["surface"]  +
            edges    * WEIGHTS["edges"]    +
            centering * WEIGHTS["centering"]
        )
        return round(score, 1)


if __name__ == "__main__":
    import argparse
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.evaluation.grader",
        description="Grade the physical condition of a Pokémon TCG card using Claude vision.",
    )
    parser.add_argument("--front", required=True, metavar="PATH",
                        help="Path to the front (recto) card image — required.")
    parser.add_argument("--back", default=None, metavar="PATH",
                        help="Path to the back (verso) card image — optional.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in environment or .env file")
        sys.exit(1)

    grader = CardGrader(api_key=api_key)
    try:
        condition = grader.grade(
            front_image_path=args.front,
            back_image_path=args.back,
        )
        print(json.dumps(
            {
                "centering": condition.centering,
                "corners": condition.corners,
                "edges": condition.edges,
                "surface": condition.surface,
                "overall_score": condition.overall_score,
                "confidence": condition.confidence,
            },
            indent=2,
        ))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
