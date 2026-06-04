"""Agent that generates optimised sale listings from a CardReport."""

import json
import sys
from typing import Optional

import anthropic

from src.models.card import CardReport

MODEL = "claude-haiku-4-5-20251001"

PLATFORM_URLS: dict[str, str] = {
    "vinted":      "https://www.vinted.fr/items/new",
    "ebay":        "https://www.ebay.fr/sell/create",
    "leboncoin":   "https://www.leboncoin.fr/deposer-une-annonce",
    "facebook":    "https://www.facebook.com/marketplace/create/item",
    "cardmarket":  "https://www.cardmarket.com/fr/Pokemon/PostProduct",
}

SUPPORTED_PLATFORMS = set(PLATFORM_URLS)

# PSA-style label from overall_score
def _condition_label(score: float) -> str:
    if score >= 9.5: return "Gem Mint (10)"
    if score >= 8.5: return "Mint (9)"
    if score >= 7.0: return "Near Mint–Mint (7–8)"
    if score >= 5.0: return "Excellent–Near Mint (5–6)"
    if score >= 3.0: return "Very Good (3–4)"
    return "Poor–Fair (1–2)"

SYSTEM_PROMPT = """You are an expert at writing optimised sales listings for collectible trading cards.
Your task is to generate a complete listing for a Pokémon TCG card based on its grading report.
You MUST respond with valid JSON only — no markdown, no explanation, no extra text."""

def _build_user_prompt(report: CardReport, platform: str, language: str) -> str:
    identity  = report.identity
    condition = report.condition
    pricing   = report.pricing

    # Grading summary
    cond_label = _condition_label(condition.overall_score)
    grading_detail = (
        f"Overall: {condition.overall_score}/10 ({cond_label}) | "
        f"Corners: {condition.corners}/10 | "
        f"Edges: {condition.edges}/10 | "
        f"Surface: {condition.surface}/10 | "
        f"Centering: {condition.centering}/10"
    )

    # Platform style instructions
    style_map = {
        "vinted": (
            "VINTED style: short punchy title (max 60 chars), "
            "fun description with relevant emojis, casual tone, "
            "finish with 5–8 hashtags (no spaces, lowercase)."
        ),
        "ebay": (
            "EBAY style: SEO-optimised title strictly under 80 characters with key search terms "
            "(card name, number, set, language, year, holo if applicable), "
            "formal detailed description with bullet points, include 'Ships tracked and insured'."
        ),
        "leboncoin": (
            "LEBONCOIN style: direct factual title, concise description (max 5 lines), "
            "firm price, specify 'Envoi en Lettre Suivie possible' or 'Remise en main propre'."
        ),
        "facebook": (
            "FACEBOOK MARKETPLACE style: conversational tone, short description (3–4 lines), "
            "friendly and approachable, mention shipping or local pickup."
        ),
        "cardmarket": (
            "CARDMARKET style: strictly factual, use standard TCG condition terminology "
            "(NM/EX/GD/LP/PL/PO), include set code and collector number, "
            "no emojis, professional seller language."
        ),
    }
    style_instruction = style_map.get(platform, style_map["vinted"])

    lang_instruction = "Write the listing in French." if language == "fr" else f"Write the listing in language code '{language}'."

    return f"""Generate a {platform.upper()} sale listing for this Pokémon TCG card.

CARD DATA:
- Name: {identity.name}
- Collector number: {identity.number}
- Set: {identity.set_name or "Unknown set"}
- Language: {identity.language}
- Rarity: {identity.rarity or "Unknown"}
- Grading: {grading_detail}
- Reference price (Near Mint): {pricing.raw_price:.2f} {pricing.currency}
- Estimated value given condition: {report.estimated_value:.2f} {pricing.currency}
- Price range: {report.value_range_low:.2f} – {report.value_range_high:.2f} {pricing.currency}

LISTING REQUIREMENTS:
- {style_instruction}
- {lang_instruction}
- Always mention: full card name + number + set + language
- Describe condition honestly using the grading scores
- Mention: "Envoi sécurisé sous sleeve + toploader"
- Mention pricing is based on recent market sales
- Suggested price = round(estimated_value) to nearest euro
- Generate 5–8 relevant platform-appropriate tags

Return ONLY this JSON object (no markdown, no extra text):
{{
  "title": "<optimised listing title>",
  "description": "<full listing description>",
  "suggested_price": <float>,
  "tags": ["tag1", "tag2", ...],
  "platform": "{platform}",
  "redirect_url": "{PLATFORM_URLS[platform]}"
}}"""


class ListingGenerator:
    """Generates optimised sale listings for Pokémon TCG cards using Claude.

    Takes a CardReport (identity + condition + pricing) and a target platform,
    and produces a ready-to-use listing dict with title, description,
    suggested price, tags, and a direct link to create the listing.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the generator with an Anthropic API key.

        Args:
            api_key: Anthropic API key for text generation requests.
        """
        self.api_key = api_key
        self._client: Optional[anthropic.Anthropic] = None

    def _build_client(self) -> anthropic.Anthropic:
        """Lazily initialise and return the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def generate(
        self,
        report: CardReport,
        platform: str,
        language: str = "fr",
    ) -> dict:
        """Generate an optimised listing for a given platform.

        Args:
            report: Full CardReport with identity, condition, and pricing.
            platform: Target platform — one of 'vinted', 'ebay', 'leboncoin',
                'facebook', 'cardmarket'.
            language: Output language code ('fr', 'en', …). Defaults to 'fr'.

        Returns:
            Dict with keys: title, description, suggested_price, tags,
            platform, redirect_url.

        Raises:
            ValueError: If platform is not in SUPPORTED_PLATFORMS or the
                model response cannot be parsed.
            anthropic.APIError: On Anthropic API failures.
        """
        platform = platform.lower().strip()
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError(
                f"Unsupported platform '{platform}'. "
                f"Choose from: {sorted(SUPPORTED_PLATFORMS)}"
            )

        client = self._build_client()
        message = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_user_prompt(report, platform, language),
            }],
        )

        raw_text = message.content[0].text
        return self._parse_response(raw_text, platform)

    def _parse_response(self, raw_response: str, platform: str) -> dict:
        """Parse and validate the model's JSON response.

        Args:
            raw_response: Raw text from Claude.
            platform: Expected platform value for validation.

        Returns:
            Validated listing dict.

        Raises:
            ValueError: If JSON is invalid or required fields are missing.
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

        required = ("title", "description", "suggested_price", "tags", "platform")
        missing = [f for f in required if f not in data]
        if missing:
            raise ValueError(f"Missing fields in listing response: {missing}")

        # Ensure redirect_url is always set correctly
        data["redirect_url"] = PLATFORM_URLS.get(platform, data.get("redirect_url", ""))

        return data


# ── Helpers for __main__ display ───────────────────────────────────────────

def _make_test_report() -> CardReport:
    """Build a fake CardReport for Dracaufeu 4/102 FR to use in tests."""
    from datetime import datetime
    from src.models.card import (
        CardIdentity, CardCondition, CardPricing, CardReport,
    )

    identity = CardIdentity(
        name="Dracaufeu",
        number="4/102",
        language="FR",
        set_name="Base Set",
        set_code="base1",
        rarity="Rare Holo",
    )
    condition = CardCondition(
        centering=7.0,
        corners=6.0,
        edges=6.5,
        surface=6.5,
        overall_score=6.5,
        confidence=0.85,
    )
    pricing = CardPricing(
        raw_price=320.0,
        grade_10=None,
        grade_9=None,
        grade_7=None,
        grade_5=None,
        grade_3=None,
        currency="EUR",
        source="tcgdex",
        last_updated=datetime.utcnow(),
        source_detail="tcgdex-only",
        language_specific=False,
        cardmarket_trend=320.0,
        tcgplayer_market=None,
    )
    return CardReport(
        identity=identity,
        condition=condition,
        pricing=pricing,
        estimated_value=210.0,
        value_range_low=168.0,
        value_range_high=252.0,
        confidence_score=0.85,
        front_image_path="data/front.jpg",
        back_image_path="data/back.jpg",
    )


def _print_listing(listing: dict) -> None:
    """Print a human-readable preview of a listing."""
    platform = listing.get("platform", "").upper()
    sep = "─" * 60
    print(f"\n{sep}")
    print(f"  📢  {platform} LISTING PREVIEW")
    print(sep)
    print(f"📌 TITRE\n   {listing['title']}")
    print(f"\n💶 PRIX SUGGÉRÉ\n   {listing['suggested_price']:.2f} EUR")
    print(f"\n📝 DESCRIPTION\n{listing['description']}")
    print(f"\n🏷️  TAGS\n   {' · '.join(listing['tags'])}")
    print(f"\n🔗 CRÉER L'ANNONCE\n   {listing['redirect_url']}")
    print(sep)


if __name__ == "__main__":
    import argparse
    import os
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.agents.listing_generator",
        description="Generate an optimised sale listing from a test CardReport.",
    )
    parser.add_argument(
        "--platform",
        default="vinted",
        choices=sorted(SUPPORTED_PLATFORMS),
        help="Target platform (default: vinted)",
    )
    parser.add_argument(
        "--language",
        default="fr",
        help="Output language code (default: fr)",
    )
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in environment or .env file")
        sys.exit(1)

    report = _make_test_report()
    generator = ListingGenerator(api_key=api_key)

    print(f"Generating listing for platform: {args.platform.upper()} …")
    try:
        listing = generator.generate(report, args.platform, args.language)
    except (ValueError, Exception) as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Raw JSON
    print("\n── JSON complet ──────────────────────────────────────────")
    print(json.dumps(listing, indent=2, ensure_ascii=False))

    # Human-readable preview
    _print_listing(listing)
