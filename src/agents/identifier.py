"""Vision agent responsible for identifying a Pokémon TCG card from an image."""

import base64
import json
import sys
from pathlib import Path
from typing import Union

import anthropic

from src.models.card import CardIdentity

MODEL = "claude-haiku-4-5-20251001"

MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

SYSTEM_PROMPT = """You are an expert Pokémon TCG card identifier.
Your task is to analyse a card image and extract structured information from it.
You MUST respond with valid JSON only — no markdown, no explanation, no extra text.
If a field is not readable or not present, use null. Never invent or guess values."""

USER_PROMPT = """Identify this Pokémon TCG card and return a JSON object with exactly these fields:

{
  "name": "<card name exactly as printed>",
  "number": "<collector number EXACTLY as printed at the bottom-right, e.g. '26/106' or '006/165'>",
  "language": "<2-letter code: EN / FR / DE / ES / IT / PT / JP / KO / ZHS / ZHT>",
  "set_name": "<official set/expansion name as printed on the card>",
  "set_code": "<short API set code if visible, otherwise null>",
  "rarity": "<rarity text or symbol if present, otherwise null>",
  "confidence": <float 0.0-1.0 reflecting your certainty>
}

Rules:
- Read the collector number EXACTLY as printed (bottom-right corner). Do not reformat it.
- Detect language from keywords printed on the card, NOT from the Pokémon name (it can be identical across languages).
  Examples: "Faiblesse"/"Résistance" → FR | "Weakness"/"Resistance" → EN | "Schwäche"/"Resistenz" → DE |
  "Debilidad"/"Resistencia" → ES | "かわいさ"/"にげる" → JP | "약점"/"저항력" → KO
- If a field is unreadable, use null — never invent a value.
- Return ONLY the JSON object, nothing else."""


class CardIdentifierAgent:
    """Uses Claude's vision capabilities to extract card identity from a photo.

    Given a raw image of a Pokémon TCG card, this agent prompts Claude to
    identify the card name, collector number, language, and set name, then
    returns a structured CardIdentity object.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the agent with an Anthropic API key.

        Args:
            api_key: Anthropic API key used to authenticate vision requests.
        """
        self.api_key = api_key
        self._client: anthropic.Anthropic | None = None

    def _build_client(self) -> anthropic.Anthropic:
        """Lazily initialise and return the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def identify(self, front_image_path: str) -> CardIdentity:
        """Analyse a card front image and return its identity.

        Identification is performed exclusively on the recto — the front face
        carries all the information needed (name, number, language, set).

        Args:
            front_image_path: Filesystem path to the front card image (JPEG, PNG, or WEBP).

        Returns:
            A CardIdentity populated with the extracted fields.

        Raises:
            FileNotFoundError: If front_image_path does not exist.
            ValueError: If the file format is unsupported or the model response
                cannot be parsed.
            anthropic.APIError: On Anthropic API failures.
        """
        path = Path(front_image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        image_data, media_type = self._load_image_as_base64(path)
        client = self._build_client()

        message = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        )

        raw_text = message.content[0].text
        return self._parse_response(raw_text)

    def _load_image_as_base64(self, image_path: Path) -> tuple[str, str]:
        """Read an image file and return (base64_data, media_type).

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64-encoded image string, MIME type string).

        Raises:
            ValueError: If the file extension is not supported.
        """
        ext = image_path.suffix.lower()
        media_type = MEDIA_TYPES.get(ext)
        if media_type is None:
            raise ValueError(
                f"Unsupported image format '{ext}'. Supported: {list(MEDIA_TYPES)}"
            )
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        return image_data, media_type

    def _parse_response(self, raw_response: str) -> CardIdentity:
        """Parse the model's JSON response into a CardIdentity.

        Args:
            raw_response: Raw text content from the Claude API response.

        Returns:
            A CardIdentity with parsed fields.

        Raises:
            ValueError: If the response is not valid JSON or required fields
                (name, number, language, set_name) are missing.
        """
        text = raw_response.strip()
        # Some models wrap JSON in markdown code fences — strip them
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

        missing = [f for f in ("name", "number", "language") if not data.get(f)]
        if missing:
            raise ValueError(f"Required fields missing or null in response: {missing}")

        return CardIdentity(
            name=data["name"],
            number=data["number"],
            language=data["language"],
            set_name=data.get("set_name") or "",
            set_code=data.get("set_code"),
            rarity=data.get("rarity"),
        )


if __name__ == "__main__":
    import argparse
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.agents.identifier",
        description="Identify a Pokémon TCG card from a photo using Claude vision.",
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

    agent = CardIdentifierAgent(api_key=api_key)
    try:
        identity = agent.identify(front_image_path=args.front)
        print(json.dumps(
            {
                "name": identity.name,
                "number": identity.number,
                "language": identity.language,
                "set_name": identity.set_name,
                "set_code": identity.set_code,
                "rarity": identity.rarity,
            },
            indent=2,
            ensure_ascii=False,
        ))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
