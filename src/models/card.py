"""Data models for the Pokémon TCG card grading pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CardIdentity:
    """Represents the identity of a Pokémon TCG card as extracted by the vision agent.

    Attributes:
        name: The Pokémon or card name (e.g. "Charizard", "Professor's Research").
        number: The card number within its set (e.g. "4/102", "006/165").
        language: The language printed on the card (e.g. "EN", "JP", "FR").
        set_name: The official TCG set name (e.g. "Base Set", "Scarlet & Violet 151").
        set_code: Optional short set identifier used by APIs (e.g. "base1", "sv3pt5").
        rarity: Optional rarity symbol or text found on the card (e.g. "Rare Holo").
    """

    name: str
    number: str
    language: str
    set_name: str
    set_code: Optional[str] = None
    rarity: Optional[str] = None


@dataclass
class CardCondition:
    """Represents the physical condition assessment of a card.

    Each sub-score (centering, corners, edges, surface) is rated 1–10.
    The overall_score is the composite grade used to map to standard
    grading tiers (PSA/BGS-style).

    Attributes:
        centering: Front/back centering score (1–10).
        corners: Corner sharpness score (1–10). Detects nicks, bends, or wear.
        edges: Edge integrity score (1–10). Detects chipping or roughness.
        surface: Surface quality score (1–10). Detects scratches, print lines,
            indentations, or staining.
        overall_score: Weighted composite score (1–10) derived from the above.
        confidence: Model confidence in the assessment (0.0–1.0).
    """

    centering: float
    corners: float
    edges: float
    surface: float
    overall_score: float
    confidence: float


@dataclass
class CardPricing:
    """Represents market pricing data retrieved for a specific card.

    Attributes:
        raw_price: Current market price for an ungraded (Near Mint) copy.
        grade_10: Market price for a PSA 10 graded copy.
        grade_9: Market price for a PSA 9 graded copy.
        grade_7: Market price for a PSA 7 graded copy.
        grade_5: Market price for a PSA 5 graded copy.
        grade_3: Market price for a PSA 3 graded copy.
        currency: ISO 4217 currency code (e.g. "USD", "EUR").
        source: Name of the pricing data provider(s).
        last_updated: Timestamp of when the pricing data was fetched.
        source_detail: Detailed source chain, e.g. "tcgdex+cardmarket-api"
            or "tcgdex-only".
        language_specific: True if raw_price is specific to the card's language
            market (e.g. FR price from CardMarket FR), False for global price.
        cardmarket_trend: CardMarket trend price (EUR), always from TCGDex layer.
        tcgplayer_market: TCGPlayer market price (USD), from TCGDex layer.
    """

    raw_price: float
    grade_10: Optional[float]
    grade_9: Optional[float]
    grade_7: Optional[float]
    grade_5: Optional[float]
    grade_3: Optional[float]
    currency: str
    source: str
    last_updated: datetime = field(default_factory=datetime.utcnow)
    source_detail: str = "tcgdex-only"
    language_specific: bool = False
    cardmarket_trend: Optional[float] = None
    tcgplayer_market: Optional[float] = None


@dataclass
class CardReport:
    """Final output report combining identity, condition, and pricing into a valuation.

    Attributes:
        identity: The identified card (name, number, set, language).
        condition: The graded physical condition of the card.
        pricing: The market pricing data for this card.
        estimated_value: Best single-point estimate of current card value given
            its condition, in the currency specified by pricing.currency.
        value_range_low: Lower bound of the estimated value range (conservative).
        value_range_high: Upper bound of the estimated value range (optimistic).
        confidence_score: Overall pipeline confidence (0.0–1.0) combining
            identification confidence and grading confidence.
        front_image_path: Path to the front (recto) image used for this report.
        back_image_path: Path to the back (verso) image if provided; None otherwise.
    """

    identity: CardIdentity
    condition: CardCondition
    pricing: CardPricing
    estimated_value: float
    value_range_low: float
    value_range_high: float
    confidence_score: float
    front_image_path: str = ""
    back_image_path: Optional[str] = None
