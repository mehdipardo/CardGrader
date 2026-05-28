"""Vision agent responsible for identifying a Pokémon TCG card from an image."""

from pathlib import Path
from typing import Union

from src.models.card import CardIdentity


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
        self._client = None  # Anthropic client, initialised on first use

    def _build_client(self):
        """Lazily initialise the Anthropic client."""
        raise NotImplementedError

    def identify(self, image_path: Union[str, Path]) -> CardIdentity:
        """Analyse a card image and return its identity.

        Sends the image to Claude with a structured prompt that asks for:
        - Card name (e.g. "Charizard")
        - Collector number (e.g. "4/102")
        - Language (e.g. "EN", "JP")
        - Set name (e.g. "Base Set")

        Args:
            image_path: Filesystem path to the card image (JPEG, PNG, or WEBP).

        Returns:
            A CardIdentity populated with the extracted fields.

        Raises:
            FileNotFoundError: If image_path does not exist.
            ValueError: If the model cannot confidently identify the card.
        """
        raise NotImplementedError

    def _load_image_as_base64(self, image_path: Path) -> tuple[str, str]:
        """Read an image file and return (base64_data, media_type).

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64-encoded image string, MIME type string).
        """
        raise NotImplementedError

    def _parse_response(self, raw_response: str) -> CardIdentity:
        """Parse the model's text response into a CardIdentity.

        Expects the model to return structured JSON or a clearly delimited
        format; extracts fields and handles missing or ambiguous values.

        Args:
            raw_response: Raw text content from the Claude API response.

        Returns:
            A CardIdentity with parsed fields.

        Raises:
            ValueError: If required fields are missing from the response.
        """
        raise NotImplementedError
