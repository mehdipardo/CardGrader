"""Tool for fetching Pokémon TCG card market prices from PokemonPriceTracker."""

import sys
from datetime import datetime
from typing import Optional

import httpx

from src.models.card import CardIdentity, CardPricing

BASE_URL = "https://www.pokemonpricetracker.com/api/v2"
SOURCE = "pokemonpricetracker"
DEFAULT_CURRENCY = "EUR"

# Timeout for API requests in seconds
REQUEST_TIMEOUT = 10.0


class CardNotFoundError(Exception):
    """Raised when the PokemonPriceTracker API finds no match for a card."""


class PricingTool:
    """Retrieves current market prices for a card across grading tiers.

    Calls the PokemonPriceTracker API to obtain raw (Near Mint) and graded
    price points (PSA/PCA tiers 3, 5, 7, 9, 10) for a given card identity.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the tool with a PokemonPriceTracker API key.

        Args:
            api_key: Bearer token for pokemonpricetracker.com authentication.
        """
        self.api_key = api_key

    def fetch_prices(self, identity: CardIdentity) -> CardPricing:
        """Fetch all available price tiers for a card.

        Queries the API using name, number, and language to uniquely identify
        the card, then maps the response to a CardPricing object.

        Args:
            identity: A CardIdentity (name, number, language are used for lookup).

        Returns:
            A CardPricing with raw and graded price points; unavailable tiers
            are set to None rather than 0.

        Raises:
            CardNotFoundError: If no card matches the identity.
            httpx.HTTPStatusError: On non-2xx API responses.
            httpx.TimeoutException: If the request exceeds REQUEST_TIMEOUT.
        """
        params = self._build_request_params(identity)
        headers = self._build_headers()

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(f"{BASE_URL}/cards", params=params, headers=headers)
            response.raise_for_status()

        data = response.json()
        return self._parse_pricing_response(data)

    def fetch_raw_price(self, identity: CardIdentity) -> float:
        """Fetch only the ungraded (Near Mint) market price for quick lookups.

        Args:
            identity: A CardIdentity for the lookup.

        Returns:
            The current raw market price as a float.

        Raises:
            CardNotFoundError: If no card matches the identity.
        """
        pricing = self.fetch_prices(identity)
        return pricing.raw_price

    def _build_request_params(self, identity: CardIdentity) -> dict:
        """Build the query parameters for the /cards endpoint.

        Args:
            identity: The card identity to build params from.

        Returns:
            Dict with name, number, and language query params.
        """
        return {
            "name": identity.name,
            "number": identity.number,
            "language": identity.language,
        }

    def _build_headers(self) -> dict:
        """Return HTTP headers including Bearer auth.

        Returns:
            Dict of request headers.
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

    def _parse_pricing_response(self, data: dict) -> CardPricing:
        """Parse the raw API response into a CardPricing object.

        Expected response shape (adjust field names if the real API differs):
        {
          "cards": [
            {
              "name": "...",
              "number": "2/102",
              "language": "FR",
              "prices": {
                "ungraded": 15.00,     # or "nm", "near_mint", "raw"
                "psa_10": 500.00,      # or "psa10", "grade_10"
                "psa_9":  200.00,
                "psa_7":  80.00,
                "psa_5":  40.00,
                "psa_3":  20.00
              }
            }
          ]
        }

        Args:
            data: The JSON body returned by the API.

        Returns:
            A populated CardPricing.

        Raises:
            CardNotFoundError: If the cards list is empty.
            KeyError: If the response shape is unexpected.
        """
        cards = data.get("cards") or data.get("data") or []
        if not cards:
            raise CardNotFoundError(
                "No card found in API response. "
                "Check name, number, and language parameters."
            )

        card = cards[0]
        prices = card.get("prices") or card.get("price") or {}

        def _price(key: str) -> Optional[float]:
            """Return float price for key, or None if absent/zero."""
            val = prices.get(key)
            return float(val) if val else None

        # Try common field name variants for each tier
        raw = (
            _price("ungraded") or _price("nm") or
            _price("near_mint") or _price("raw") or 0.0
        )

        return CardPricing(
            raw_price=raw,
            grade_10=_price("psa_10") or _price("psa10") or _price("grade_10"),
            grade_9 =_price("psa_9")  or _price("psa9")  or _price("grade_9"),
            grade_7 =_price("psa_7")  or _price("psa7")  or _price("grade_7"),
            grade_5 =_price("psa_5")  or _price("psa5")  or _price("grade_5"),
            grade_3 =_price("psa_3")  or _price("psa3")  or _price("grade_3"),
            currency=card.get("currency", DEFAULT_CURRENCY),
            source=SOURCE,
            last_updated=datetime.utcnow(),
        )


if __name__ == "__main__":
    import argparse
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.tools.pricing",
        description="Fetch market prices for a Pokémon TCG card.",
    )
    parser.add_argument("--name",     required=True, help="Card name (e.g. 'Tortank')")
    parser.add_argument("--number",   required=True, help="Collector number (e.g. '2/102')")
    parser.add_argument("--language", required=True, help="Language code (e.g. 'FR', 'EN')")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("POKEMON_TCG_API_KEY")
    if not api_key:
        print("Error: POKEMON_TCG_API_KEY not set in environment or .env file")
        sys.exit(1)

    tool = PricingTool(api_key=api_key)
    identity = CardIdentity(
        name=args.name,
        number=args.number,
        language=args.language,
        set_name="",
    )

    try:
        pricing = tool.fetch_prices(identity)
        import json
        print(json.dumps(
            {
                "raw_price":   pricing.raw_price,
                "grade_10":    pricing.grade_10,
                "grade_9":     pricing.grade_9,
                "grade_7":     pricing.grade_7,
                "grade_5":     pricing.grade_5,
                "grade_3":     pricing.grade_3,
                "currency":    pricing.currency,
                "source":      pricing.source,
                "last_updated": pricing.last_updated.isoformat(),
            },
            indent=2,
        ))
    except CardNotFoundError as e:
        print(f"Card not found: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"API error {e.response.status_code}: {e.response.text}")
        sys.exit(1)
    except httpx.TimeoutException:
        print("Error: API request timed out")
        sys.exit(1)
