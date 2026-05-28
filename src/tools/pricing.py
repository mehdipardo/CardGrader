"""Tool for fetching Pokémon TCG card market prices from PokeTrace."""

import json
import sys
from datetime import datetime
from typing import Optional

import httpx

from src.models.card import CardIdentity, CardPricing

BASE_URL = "https://api.poketrace.com/v1"
SOURCE = "poketrace"
DEFAULT_CURRENCY = "USD"
REQUEST_TIMEOUT = 10.0


class CardNotFoundError(Exception):
    """Raised when PokeTrace returns no card matching the requested identity."""


def _normalize_number(number: str) -> str:
    """Strip leading zeros from each part of a card number for comparison.

    Examples:
        "002/102" -> "2/102"
        "026/106" -> "26/106"
        "2/102"   -> "2/102"
    """
    parts = number.split("/")
    return "/".join(str(int(p)) if p.isdigit() else p for p in parts)


def _number_matches(api_number: str, identity_number: str) -> bool:
    """Return True when api_number and identity_number refer to the same card.

    Handles zero-padding differences (e.g. "002/102" vs "2/102").
    """
    return _normalize_number(api_number) == _normalize_number(identity_number)


def _get_price(prices: dict, market: str, condition: str = "NEAR_MINT") -> Optional[float]:
    """Safely extract prices[market][condition]['avg'], or None if absent."""
    try:
        val = prices[market][condition]["avg"]
        return float(val) if val is not None else None
    except (KeyError, TypeError, ValueError):
        return None


class PricingTool:
    """Retrieves current market prices for a card from PokeTrace.

    Uses PokeTrace's /v1/cards endpoint to find a card by name, then matches
    the correct result using the collector number. raw_price is sourced from
    eBay (NEAR_MINT avg), falling back to TCGPlayer if eBay data is absent.

    PSA/PCA graded prices are not provided by the PokeTrace free tier and are
    set to None; they can be populated from a future graded-sales endpoint.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the tool with a PokeTrace API key.

        Args:
            api_key: PokeTrace API key (X-API-Key header).
        """
        self.api_key = api_key

    def fetch_prices(self, identity: CardIdentity) -> CardPricing:
        """Fetch market prices for a card.

        Searches by name, then selects the result whose cardNumber matches
        identity.number (zero-padding tolerant). raw_price prefers eBay,
        falls back to TCGPlayer.

        Args:
            identity: CardIdentity — name, number, and language are used.

        Returns:
            A CardPricing with raw_price set and grade tiers as None (not
            available on free tier).

        Raises:
            CardNotFoundError: If no result matches the card number.
            httpx.HTTPStatusError: On non-2xx API responses.
            httpx.TimeoutException: If the request exceeds REQUEST_TIMEOUT.
        """
        params = self._build_request_params(identity)
        headers = self._build_headers()

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(f"{BASE_URL}/cards", params=params, headers=headers)
            response.raise_for_status()

        data = response.json()
        return self._parse_pricing_response(data, identity)

    def fetch_raw_price(self, identity: CardIdentity) -> float:
        """Fetch only the ungraded (Near Mint) market price.

        Args:
            identity: A CardIdentity for the lookup.

        Returns:
            The current raw market price as a float.

        Raises:
            CardNotFoundError: If no card matches the identity.
        """
        return self.fetch_prices(identity).raw_price

    def _build_request_params(self, identity: CardIdentity) -> dict:
        """Build query parameters for the /v1/cards endpoint.

        Args:
            identity: Source of the search term.

        Returns:
            Dict with search, limit, and market params.
        """
        return {
            "search": identity.name,
            "limit": 10,
            "market": "US",
        }

    def _build_headers(self) -> dict:
        """Return HTTP headers including the X-API-Key auth header.

        Returns:
            Dict of request headers.
        """
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

    def _parse_pricing_response(self, data: dict, identity: CardIdentity) -> CardPricing:
        """Find the matching card in the API response and build a CardPricing.

        Matches on cardNumber (zero-padding tolerant via _number_matches).
        raw_price = eBay NEAR_MINT avg, fallback to TCGPlayer NEAR_MINT avg.
        PSA grade tiers are None (not in free tier response).

        Args:
            data: Parsed JSON body from the /v1/cards endpoint.
            identity: Used to match the correct card by number.

        Returns:
            A populated CardPricing.

        Raises:
            CardNotFoundError: If no card in data matches identity.number.
        """
        cards = data.get("data") or []

        matched = next(
            (c for c in cards if _number_matches(c.get("cardNumber", ""), identity.number)),
            None,
        )

        if matched is None:
            numbers = [c.get("cardNumber") for c in cards]
            raise CardNotFoundError(
                f"No card with number '{identity.number}' found among API results: {numbers}"
            )

        prices = matched.get("prices") or {}

        ebay_nm    = _get_price(prices, "ebay",      "NEAR_MINT")
        tcg_nm     = _get_price(prices, "tcgplayer", "NEAR_MINT")
        raw_price  = ebay_nm if ebay_nm is not None else (tcg_nm or 0.0)

        return CardPricing(
            raw_price=raw_price,
            # Graded prices not available on PokeTrace free tier
            grade_10=None,
            grade_9=None,
            grade_7=None,
            grade_5=None,
            grade_3=None,
            currency=DEFAULT_CURRENCY,
            source=SOURCE,
            last_updated=datetime.utcnow(),
        )


if __name__ == "__main__":
    import argparse
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.tools.pricing",
        description="Fetch market prices for a Pokémon TCG card via PokeTrace.",
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
    identity = CardIdentity(name=args.name, number=args.number, language=args.language, set_name="")

    try:
        pricing = tool.fetch_prices(identity)
        print(json.dumps(
            {
                "raw_price":    pricing.raw_price,
                "grade_10":     pricing.grade_10,
                "grade_9":      pricing.grade_9,
                "grade_7":      pricing.grade_7,
                "grade_5":      pricing.grade_5,
                "grade_3":      pricing.grade_3,
                "currency":     pricing.currency,
                "source":       pricing.source,
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
