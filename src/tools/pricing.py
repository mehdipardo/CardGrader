"""Tool for fetching Pokémon TCG card market prices from free sources."""

import re
import sys
import time
from datetime import datetime
from statistics import median
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.models.card import CardIdentity, CardPricing

BASE_URL = "https://www.pokemonpricetracker.com/api/v2"
EBAY_SEARCH_URL = "https://www.ebay.fr/sch/i.html"
SOURCE = "pokemonpricetracker+ebay"
DEFAULT_CURRENCY = "EUR"
PSA_GRADES = (10, 9, 7, 5, 3)

REQUEST_TIMEOUT = 10.0
EBAY_REQUEST_TIMEOUT = 15.0
EBAY_DELAY_SECONDS = 1.0

EBAY_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class CardNotFoundError(Exception):
    """Raised when no matching card can be found in the pricing sources."""


class PricingTool:
    """Retrieves market prices by combining PokemonPriceTracker and eBay sold listings.

    Raw (Near Mint) price comes from the PokemonPriceTracker free API.
    Graded PSA prices are estimated from the median of recent eBay completed sales.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the tool with a PokemonPriceTracker API key.

        Args:
            api_key: Bearer token for pokemonpricetracker.com authentication.
        """
        self.api_key = api_key

    def fetch_prices(self, identity: CardIdentity) -> CardPricing:
        """Fetch raw and graded price tiers for a card.

        Args:
            identity: Card identity (name, number, language used for lookup).

        Returns:
            CardPricing with raw_price from PokemonPriceTracker and graded
            tiers from eBay sold listings (None when insufficient data).

        Raises:
            CardNotFoundError: If PokemonPriceTracker returns no matching card.
            httpx.HTTPStatusError: On non-2xx API responses.
            httpx.TimeoutException: If a request exceeds its timeout.
        """
        raw_price = self._fetch_raw_price(identity)
        graded: dict[int, Optional[float]] = {}
        for i, grade in enumerate(PSA_GRADES):
            if i > 0:
                time.sleep(EBAY_DELAY_SECONDS)
            graded[grade] = self._fetch_ebay_grade_median(identity, grade)

        return CardPricing(
            raw_price=raw_price,
            grade_10=graded[10],
            grade_9=graded[9],
            grade_7=graded[7],
            grade_5=graded[5],
            grade_3=graded[3],
            currency=DEFAULT_CURRENCY,
            source=SOURCE,
            last_updated=datetime.utcnow(),
        )

    def fetch_raw_price(self, identity: CardIdentity) -> float:
        """Fetch only the ungraded (Near Mint) market price."""
        return self._fetch_raw_price(identity)

    def _fetch_raw_price(self, identity: CardIdentity) -> float:
        """Query PokemonPriceTracker and return the matched card's market price."""
        params = {
            "search": identity.name,
            "language": self._ppt_language(identity.language),
            "limit": 10,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            response = client.get(f"{BASE_URL}/cards", params=params, headers=headers)
            response.raise_for_status()

        data = response.json()
        cards = data.get("data") or []
        if not cards:
            raise CardNotFoundError(
                f"No results from PokemonPriceTracker for {identity.name!r}."
            )

        card = self._match_card_by_number(cards, identity.number)
        if card is None:
            raise CardNotFoundError(
                f"No card matching number {identity.number!r} "
                f"among {len(cards)} PokemonPriceTracker result(s)."
            )

        prices = card.get("prices") or {}
        market = prices.get("market")
        if market is None:
            raise CardNotFoundError(
                f"Card {identity.number!r} found but prices.market is missing."
            )
        return float(market)

    def _extract_card_number(self, card: dict) -> str:
        """Build a collector number string from API fields."""
        if card.get("number"):
            return str(card["number"]).strip()
        card_number = card.get("cardNumber")
        total_set = card.get("totalSetNumber")
        if card_number is not None and total_set is not None:
            return f"{card_number}/{total_set}"
        if card_number is not None:
            return str(card_number).strip()
        return ""

    def _normalize_collector_number(self, number: str) -> str:
        """Normalize collector numbers for comparison (e.g. 02/102 → 2/102)."""
        cleaned = number.strip().lower().replace(" ", "")
        if "/" not in cleaned:
            return cleaned
        left, right = cleaned.split("/", 1)
        left = left.lstrip("0") or "0"
        right = right.lstrip("0") or "0"
        return f"{left}/{right}"

    def _match_card_by_number(
        self, cards: list[dict], target_number: str
    ) -> Optional[dict]:
        """Return the first card whose collector number matches target_number."""
        target = self._normalize_collector_number(target_number)
        for card in cards:
            candidate = self._normalize_collector_number(self._extract_card_number(card))
            if candidate and candidate == target:
                return card
        return None

    def _ppt_language(self, language: str) -> str:
        """Map a 2-letter language code to the PokemonPriceTracker language param.

        The free API only accepts ``english`` and ``japanese``; French and other
        languages fall back to ``english`` (search still uses the printed name).
        """
        code = language.strip().upper()
        if code == "JP":
            return "japanese"
        return "english"

    def _fetch_ebay_grade_median(
        self, identity: CardIdentity, grade: int
    ) -> Optional[float]:
        """Scrape eBay sold listings and return the median of recent sale prices."""
        query = f"{identity.name} {identity.number} PSA {grade} pokemon"
        params = {
            "_nkw": query,
            "LH_Sold": "1",
            "LH_Complete": "1",
            "_sacat": "0",
        }

        try:
            with httpx.Client(
                timeout=EBAY_REQUEST_TIMEOUT,
                headers=EBAY_HEADERS,
                follow_redirects=True,
            ) as client:
                response = client.get(EBAY_SEARCH_URL, params=params)
                response.raise_for_status()
        except httpx.HTTPError:
            return None

        prices = self._parse_ebay_prices(response.text)
        return self._median_of_recent_sales(prices)

    def _parse_ebay_prices(self, html: str) -> list[float]:
        """Extract numeric sale prices from eBay search result HTML."""
        soup = BeautifulSoup(html, "html.parser")
        parsed: list[float] = []

        for element in soup.select(".s-item__price"):
            text = element.get_text(strip=True)
            lower = text.lower()
            if not text or ("enchère" in lower and "à" in lower):
                continue
            price = self._clean_price(text)
            if price is not None and price > 0:
                parsed.append(price)

        return parsed

    def _clean_price(self, text: str) -> Optional[float]:
        """Parse a price string like '45,50 EUR' or '$12.99' into a float."""
        text = text.strip()
        for token in ("EUR", "USD", "GBP", "€", "$", "£"):
            text = text.replace(token, "")
        text = text.strip()

        match = re.search(r"[\d\s.,]+", text)
        if not match:
            return None

        numeric = match.group(0).strip().replace(" ", "")
        if not numeric:
            return None

        if "," in numeric and "." in numeric:
            if numeric.rfind(",") > numeric.rfind("."):
                numeric = numeric.replace(".", "").replace(",", ".")
            else:
                numeric = numeric.replace(",", "")
        elif "," in numeric:
            parts = numeric.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                numeric = numeric.replace(",", ".")
            else:
                numeric = numeric.replace(",", "")

        try:
            return float(numeric)
        except ValueError:
            return None

    def _median_of_recent_sales(self, prices: list[float]) -> Optional[float]:
        """Return the median of up to 5 recent sales, or None if fewer than 3."""
        recent = prices[:5]
        if len(recent) < 3:
            return None
        return float(median(recent))


if __name__ == "__main__":
    import argparse
    import json
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.tools.pricing",
        description="Fetch market prices for a Pokémon TCG card (free sources).",
    )
    parser.add_argument("--name", required=True, help="Card name (e.g. 'Tortank')")
    parser.add_argument("--number", required=True, help="Collector number (e.g. '2/102')")
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
        print(f"Fetching prices for {identity.name} ({identity.number}, {identity.language})...")
        pricing = tool.fetch_prices(identity)
        print(json.dumps(
            {
                "raw_price": pricing.raw_price,
                "grade_10": pricing.grade_10,
                "grade_9": pricing.grade_9,
                "grade_7": pricing.grade_7,
                "grade_5": pricing.grade_5,
                "grade_3": pricing.grade_3,
                "currency": pricing.currency,
                "source": pricing.source,
                "last_updated": pricing.last_updated.isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        ))
    except CardNotFoundError as e:
        print(f"Card not found: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error {e.response.status_code}: {e.response.text[:500]}")
        sys.exit(1)
    except httpx.TimeoutException:
        print("Error: request timed out")
        sys.exit(1)
