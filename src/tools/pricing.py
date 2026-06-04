"""Two-layer pricing tool: TCGDex (always) + cardmarket-api via RapidAPI (optional)."""

import sys
from datetime import datetime
from typing import Optional

import httpx

from src.models.card import CardIdentity, CardPricing

# Layer 2 endpoint — RapidAPI cardmarket pokemon API
RAPIDAPI_URL = "https://pokemon-api2.p.rapidapi.com/cards"
RAPIDAPI_HOST = "pokemon-api2.p.rapidapi.com"
REQUEST_TIMEOUT = 10.0

# Languages that have dedicated CardMarket regional prices
REGIONAL_LANGUAGES = {"FR", "JP", "DE", "IT", "ES"}

SOURCE_TCGDEX_ONLY = "tcgdex-only"
SOURCE_TCGDEX_RAPID = "tcgdex+cardmarket-api"


class PricingTool:
    """Retrieves market prices via two complementary layers.

    Layer 1 — TCGDex (always called, free, no key):
        Provides CardMarket trend/avg and TCGPlayer market prices embedded
        in the card dict returned by CardLookupTool.resolve().

    Layer 2 — cardmarket-api.com via RapidAPI (optional, keyed):
        Provides language-specific CardMarket prices (FR, DE, JP…) and
        PSA/eBay graded sale data. Only called when RAPIDAPI_KEY is set
        and the card's language is in REGIONAL_LANGUAGES.
        On 429 (quota exceeded) the layer is skipped silently.
    """

    def __init__(self, rapidapi_key: Optional[str] = None) -> None:
        """Initialise the pricing tool.

        Args:
            rapidapi_key: RapidAPI key for cardmarket-api.com. Optional —
                the tool functions with TCGDex data alone when absent.
        """
        self.rapidapi_key = rapidapi_key

    def fetch_prices(
        self,
        identity: CardIdentity,
        tcgdex_card: dict,
    ) -> CardPricing:
        """Fetch a complete CardPricing from TCGDex data + optional RapidAPI enrichment.

        Args:
            identity: Card identity (language used for regional pricing).
            tcgdex_card: Full card dict returned by CardLookupTool.resolve().

        Returns:
            A CardPricing with raw_price, optional grade tiers, and metadata.
        """
        pricing_data = tcgdex_card.get("pricing") or {}
        is_holo = self._is_holo(tcgdex_card)

        # ── Layer 1: TCGDex ────────────────────────────────────────────────
        cm_trend  = self._extract_cardmarket_trend(pricing_data, is_holo)
        tcp_market = self._extract_tcgplayer_market(pricing_data)

        raw_price = cm_trend or tcp_market or 0.0
        currency  = "EUR" if cm_trend is not None else "USD"
        source_detail = SOURCE_TCGDEX_ONLY
        language_specific = False
        grade_10 = grade_9 = grade_7 = grade_5 = grade_3 = None

        # ── Layer 2: RapidAPI (optional) ───────────────────────────────────
        if self.rapidapi_key and identity.language in REGIONAL_LANGUAGES:
            card_id = tcgdex_card.get("id", "")
            rapid_data = self._fetch_rapidapi(card_id)
            if rapid_data:
                lang_price = self._extract_language_specific_price(rapid_data, identity.language)
                if lang_price is not None:
                    raw_price = lang_price
                    language_specific = True

                graded = self._extract_graded_prices(rapid_data)
                grade_10 = graded.get(10)
                grade_9  = graded.get(9)
                grade_7  = graded.get(7)
                grade_5  = graded.get(5)
                grade_3  = graded.get(3)
                source_detail = SOURCE_TCGDEX_RAPID

        return CardPricing(
            raw_price=raw_price,
            grade_10=grade_10,
            grade_9=grade_9,
            grade_7=grade_7,
            grade_5=grade_5,
            grade_3=grade_3,
            currency=currency,
            source="tcgdex" if source_detail == SOURCE_TCGDEX_ONLY else "tcgdex+rapidapi",
            last_updated=datetime.utcnow(),
            source_detail=source_detail,
            language_specific=language_specific,
            cardmarket_trend=cm_trend,
            tcgplayer_market=tcp_market,
        )

    # ── Layer 1 helpers ────────────────────────────────────────────────────

    def _extract_tcgdex_price(self, pricing_data: dict, is_holo: bool) -> float:
        """Extract the best available price from TCGDex pricing block.

        Priority: CardMarket trend-holo (if holo) > trend > avg > low >
                  TCGPlayer holo.marketPrice > normal.marketPrice.

        Args:
            pricing_data: The 'pricing' dict from a TCGDex card record.
            is_holo: Whether the card is holographic.

        Returns:
            Best available price as float, or 0.0 if no data found.
        """
        return self._extract_cardmarket_trend(pricing_data, is_holo) \
            or self._extract_tcgplayer_market(pricing_data) \
            or 0.0

    def _extract_cardmarket_trend(
        self, pricing_data: dict, is_holo: bool = False
    ) -> Optional[float]:
        """Return CardMarket trend (or avg) price from TCGDex pricing data."""
        cm = pricing_data.get("cardmarket") or {}
        if is_holo:
            price = cm.get("trend-holo") or cm.get("avg-holo") \
                 or cm.get("trend")      or cm.get("avg") or cm.get("low")
        else:
            price = cm.get("trend") or cm.get("avg") or cm.get("low")
        return float(price) if price else None

    def _extract_tcgplayer_market(self, pricing_data: dict) -> Optional[float]:
        """Return TCGPlayer market price from TCGDex pricing data."""
        tcp = pricing_data.get("tcgplayer") or {}
        for variant in ("holo", "reverse", "normal"):
            market = (tcp.get(variant) or {}).get("marketPrice")
            if market:
                return float(market)
        return None

    @staticmethod
    def _is_holo(tcgdex_card: dict) -> bool:
        """Return True if the card variant is holographic."""
        rarity = (tcgdex_card.get("rarity") or "").lower()
        return "holo" in rarity or "rare h" in rarity

    # ── Layer 2 helpers ────────────────────────────────────────────────────

    def _fetch_rapidapi(self, card_id: str) -> Optional[dict]:
        """Call cardmarket-api.com via RapidAPI for a card.

        Returns the parsed JSON dict, or None on 429 (quota) or any error.

        Args:
            card_id: TCGDex card ID used as the lookup key.
        """
        headers = {
            "X-RapidAPI-Key":  self.rapidapi_key,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        }
        try:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                resp = client.get(f"{RAPIDAPI_URL}/{card_id}", headers=headers)
            if resp.status_code == 429:
                return None  # quota exceeded — degrade gracefully
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException):
            return None

    def _extract_language_specific_price(
        self, data: dict, language: str
    ) -> Optional[float]:
        """Extract a language-specific CardMarket price from RapidAPI response.

        Looks for 'lowest_near_mint_{LANG}' in prices.cardmarket.

        Args:
            data: Parsed RapidAPI response dict.
            language: 2-letter language code (e.g. "FR", "DE").

        Returns:
            The language-specific price, or None if absent.
        """
        try:
            key = f"lowest_near_mint_{language}"
            val = data["prices"]["cardmarket"].get(key)
            return float(val) if val is not None else None
        except (KeyError, TypeError, ValueError):
            return None

    def _extract_graded_prices(self, data: dict) -> dict[int, Optional[float]]:
        """Extract PSA graded prices from RapidAPI response.

        Prefers CardMarket PSA data; falls back to eBay median when the
        eBay sample has at least 3 sales.

        Args:
            data: Parsed RapidAPI response dict.

        Returns:
            Dict mapping grade tier (10/9/7/5/3) to price or None.
        """
        result: dict[int, Optional[float]] = {10: None, 9: None, 7: None, 5: None, 3: None}

        try:
            psa = data["prices"]["cardmarket"]["graded"]["psa"]
            for grade, key in ((10, "psa10"), (9, "psa9")):
                val = psa.get(key)
                if val:
                    result[grade] = float(val)
        except (KeyError, TypeError):
            pass

        try:
            ebay_psa = data["prices"]["ebay"]["graded"]["psa"]
            for grade in (10, 9, 7, 5, 3):
                entry = ebay_psa.get(str(grade)) or {}
                if (entry.get("sample_size") or 0) >= 3:
                    median_p = entry.get("median_price")
                    if median_p and result[grade] is None:
                        result[grade] = float(median_p)
        except (KeyError, TypeError):
            pass

        return result


if __name__ == "__main__":
    import argparse
    import json
    import os

    from dotenv import load_dotenv

    from src.tools.card_lookup import CardLookupTool, CardNotFoundError

    parser = argparse.ArgumentParser(
        prog="python -m src.tools.pricing",
        description="Fetch market prices for a Pokémon TCG card.",
    )
    parser.add_argument("--name",     required=True, help="Card name (e.g. 'Tortank')")
    parser.add_argument("--number",   required=True, help="Collector number (e.g. '2/102')")
    parser.add_argument("--language", required=True, help="Language code (e.g. 'FR', 'EN')")
    args = parser.parse_args()

    load_dotenv()
    rapidapi_key = os.environ.get("RAPIDAPI_KEY")

    identity = CardIdentity(name=args.name, number=args.number, language=args.language, set_name="")

    try:
        tcgdex_card = CardLookupTool().resolve(identity)
        pricing = PricingTool(rapidapi_key=rapidapi_key).fetch_prices(identity, tcgdex_card)
        print(json.dumps(
            {
                "raw_price":        pricing.raw_price,
                "currency":         pricing.currency,
                "grade_10":         pricing.grade_10,
                "grade_9":          pricing.grade_9,
                "grade_7":          pricing.grade_7,
                "grade_5":          pricing.grade_5,
                "grade_3":          pricing.grade_3,
                "source_detail":    pricing.source_detail,
                "language_specific":pricing.language_specific,
                "cardmarket_trend": pricing.cardmarket_trend,
                "tcgplayer_market": pricing.tcgplayer_market,
                "last_updated":     pricing.last_updated.isoformat(),
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
