"""TCGDex card lookup tool — resolves card identity and baseline prices."""

import sys
from typing import Optional

import httpx

from src.models.card import CardIdentity

BASE_URL = "https://api.tcgdex.net/v2"
REQUEST_TIMEOUT = 10.0

LANGUAGE_TO_TCGDEX: dict[str, str] = {
    "FR": "fr",
    "EN": "en",
    "JP": "ja",
    "DE": "de",
    "IT": "it",
    "ES": "es",
    "KO": "ko",
    "PT": "pt",
}


class CardNotFoundError(Exception):
    """Raised when TCGDex finds no card matching the requested identity."""


def _normalize_number(number: str) -> str:
    """Strip leading zeros from each part of a collector number.

    Examples: "002/102" → "2/102", "026/106" → "26/106".
    """
    parts = number.split("/")
    return "/".join(str(int(p)) if p.isdigit() else p for p in parts)


def _number_matches(identity_number: str, tcgdex_local_id: str) -> bool:
    """Return True if identity_number corresponds to a TCGdex localId.

    The vision agent produces full collector numbers like "2/102" or "002/102",
    while TCGdex localId is just the set-local part like "2".
    Matching rules (both sides are zero-stripped):
      "2/102"   == "2"     → True   (strip /total)
      "002/102" == "2"     → True   (strip /total + zeros)
      "26/106"  == "26"    → True
      "2/102"   == "2/102" → True   (exact match kept as fallback)
      "2/102"   == "3"     → False
    """
    def _norm(s: str) -> str:
        return str(int(s)) if s.isdigit() else s.lower()

    norm_local = _norm(tcgdex_local_id)

    # Exact normalized match ("2" == "2")
    if _norm(identity_number) == norm_local:
        return True

    # Match local part before "/" ("2/102" → "2")
    local_part = identity_number.split("/")[0]
    return _norm(local_part) == norm_local


class CardLookupTool:
    """Resolves a CardIdentity to a full TCGDex card record.

    TCGDex is a free, keyless, multilingual API. The resolved card dict
    includes set metadata, rarity, and a 'pricing' block with CardMarket
    and TCGPlayer data — used downstream by PricingTool.

    Lookup strategy:
      1. Search by name in the card's language → list of card stubs
      2. Match on normalised collector number
      3. Fetch the full card by ID to get pricing and all metadata
    """

    def __init__(self) -> None:
        """No API key required — TCGDex is publicly accessible."""

    def resolve(self, identity: CardIdentity) -> dict:
        """Resolve a CardIdentity to a full TCGDex card record.

        Args:
            identity: CardIdentity from the vision agent.

        Returns:
            Full TCGDex card dict including 'pricing', 'set', 'rarity', etc.

        Raises:
            CardNotFoundError: If no card matches the name + number.
            httpx.HTTPStatusError: On non-2xx API responses.
            httpx.TimeoutException: If a request exceeds REQUEST_TIMEOUT.
        """
        lang = LANGUAGE_TO_TCGDEX.get(identity.language, "en")

        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            # Step 1 — search by name
            resp = client.get(
                f"{BASE_URL}/{lang}/cards",
                params={"name": identity.name},
            )
            resp.raise_for_status()
            candidates = resp.json()

        if not isinstance(candidates, list) or not candidates:
            raise CardNotFoundError(
                f"No cards found for name '{identity.name}' (lang={lang})"
            )

        # Step 2 — match on localId using _number_matches
        # TCGdex search stubs expose only localId (e.g. "2"), not the full
        # collector number ("2/102") — _number_matches handles the difference.
        matched_id: Optional[str] = None
        for card in candidates:
            local_id = str(card.get("localId") or card.get("id", ""))
            if _number_matches(identity.number, local_id):
                matched_id = card.get("id")
                break

        if matched_id is None:
            found = [str(c.get("localId") or c.get("id", "")) for c in candidates[:10]]
            raise CardNotFoundError(
                f"No card with number '{identity.number}' among TCGDex results "
                f"for '{identity.name}'. localIds found: {found}"
            )

        # Step 3 — fetch full card by ID
        return self.get_card_by_id(matched_id, language=lang)

    def get_card_by_id(self, card_id: str, language: str = "en") -> dict:
        """Fetch a full TCGDex card record by its global ID.

        Args:
            card_id: TCGDex global card ID (e.g. "base1-2").
            language: TCGDex language prefix (e.g. "fr", "en", "ja").

        Returns:
            Full card dict with pricing, set, rarity, and image fields.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
        """
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(f"{BASE_URL}/{language}/cards/{card_id}")
            resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="python -m src.tools.card_lookup",
        description="Resolve a Pokémon TCG card via TCGDex (no API key required).",
    )
    parser.add_argument("--name",     required=True, help="Card name (e.g. 'Tortank')")
    parser.add_argument("--number",   required=True, help="Collector number (e.g. '2/102')")
    parser.add_argument("--language", required=True, help="Language code (e.g. 'FR', 'EN')")
    args = parser.parse_args()

    tool = CardLookupTool()
    identity = CardIdentity(
        name=args.name,
        number=args.number,
        language=args.language,
        set_name="",
    )

    try:
        card = tool.resolve(identity)
        print(json.dumps(card, indent=2, ensure_ascii=False))
    except CardNotFoundError as e:
        print(f"Card not found: {e}")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"API error {e.response.status_code}: {e.response.text}")
        sys.exit(1)
    except httpx.TimeoutException:
        print("Error: TCGDex request timed out")
        sys.exit(1)
