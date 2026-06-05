"""Unit tests for the two-layer pricing tool (no live API calls)."""

from src.tools.pricing import PricingTool, SOURCE_TCGDEX_ONLY, SOURCE_TCGDEX_RAPID
from src.tools.card_lookup import _normalize_number, _number_matches


# ── card_lookup helpers ────────────────────────────────────────────────────

def test_normalize_strips_leading_zeros():
    assert _normalize_number("002/102") == "2/102"
    assert _normalize_number("026/106") == "26/106"
    assert _normalize_number("2/102")   == "2/102"
    assert _normalize_number("100/100") == "100/100"


def test_number_matches_strips_set_total():
    assert _number_matches("2/102",   "2")   is True
    assert _number_matches("002/102", "2")   is True
    assert _number_matches("26/106",  "26")  is True
    assert _number_matches("2/102",   "2/102") is True  # exact fallback
    assert _number_matches("2/102",   "3")   is False
    assert _number_matches("10/102",  "1")   is False


# ── TCGDex layer ───────────────────────────────────────────────────────────

def _make_tcgdex_card(cm=None, tcp=None, rarity="Rare Holo"):
    pricing = {}
    if cm:
        pricing["cardmarket"] = cm
    if tcp:
        pricing["tcgplayer"] = tcp
    return {"id": "base1-2", "rarity": rarity, "pricing": pricing}


def test_cardmarket_trend_preferred():
    tool = PricingTool()
    card = _make_tcgdex_card(cm={"trend": 42.0, "avg": 30.0})
    assert tool._extract_cardmarket_trend(card["pricing"]) == 42.0


def test_cardmarket_avg_fallback():
    tool = PricingTool()
    card = _make_tcgdex_card(cm={"avg": 30.0})
    assert tool._extract_cardmarket_trend(card["pricing"]) == 30.0


def test_holo_trend_preferred_over_regular_trend():
    tool = PricingTool()
    card = _make_tcgdex_card(cm={"trend": 42.0, "trend-holo": 60.0})
    assert tool._extract_cardmarket_trend(card["pricing"], is_holo=True) == 60.0


def test_tcgplayer_fallback_when_no_cardmarket():
    tool = PricingTool()
    card = _make_tcgdex_card(tcp={"holo": {"marketPrice": 55.0}})
    assert tool._extract_tcgplayer_market(card["pricing"]) == 55.0


def test_fetch_prices_tcgdex_only():
    from src.models.card import CardIdentity
    tool = PricingTool(rapidapi_key=None)
    identity = CardIdentity(name="Blastoise", number="2/102", language="EN", set_name="")
    card = _make_tcgdex_card(cm={"trend": 42.0, "unit": "EUR"})
    pricing = tool.fetch_prices(identity, card)
    assert pricing.raw_price == 42.0
    assert pricing.currency == "EUR"
    assert pricing.source_detail == SOURCE_TCGDEX_ONLY
    assert pricing.language_specific is False
    assert pricing.grade_10 is None


def test_fetch_prices_no_pricing_block_gives_zero():
    from src.models.card import CardIdentity
    tool = PricingTool()
    identity = CardIdentity(name="X", number="1/10", language="EN", set_name="")
    pricing = tool.fetch_prices(identity, {"id": "x-1", "pricing": {}})
    assert pricing.raw_price == 0.0


# ── RapidAPI layer helpers ─────────────────────────────────────────────────

def test_extract_language_specific_price_fr():
    tool = PricingTool(rapidapi_key="test")
    data = {"prices": {"cardmarket": {"lowest_near_mint_FR": 38.0}}}
    assert tool._extract_language_specific_price(data, "FR") == 38.0


def test_extract_language_specific_price_missing():
    tool = PricingTool(rapidapi_key="test")
    data = {"prices": {"cardmarket": {}}}
    assert tool._extract_language_specific_price(data, "FR") is None


def test_extract_graded_prices_from_ebay():
    tool = PricingTool(rapidapi_key="test")
    data = {
        "prices": {
            "cardmarket": {},
            "ebay": {
                "graded": {
                    "psa": {
                        "10": {"median_price": 550, "sample_size": 5},
                        "9":  {"median_price": 220, "sample_size": 4},
                        "7":  {"median_price": 80,  "sample_size": 2},  # sample too small
                    }
                }
            }
        }
    }
    graded = tool._extract_graded_prices(data)
    assert graded[10] == 550.0
    assert graded[9]  == 220.0
    assert graded[7]  is None  # sample_size < 3


def test_extract_graded_prices_empty():
    tool = PricingTool(rapidapi_key="test")
    graded = tool._extract_graded_prices({})
    assert all(v is None for v in graded.values())


# ── Scoring ────────────────────────────────────────────────────────────────

def test_score_to_grade_tier_mapping():
    from src.evaluation.scoring import ScoringEngine
    engine = ScoringEngine()
    assert engine.map_score_to_grade_tier(9.8) == 10
    assert engine.map_score_to_grade_tier(9.0) == 9
    assert engine.map_score_to_grade_tier(7.5) == 7
    assert engine.map_score_to_grade_tier(6.0) == 5
    assert engine.map_score_to_grade_tier(4.0) == 3
    assert engine.map_score_to_grade_tier(2.0) == 1


def test_value_range_widens_with_low_confidence():
    from src.evaluation.scoring import ScoringEngine
    from src.models.card import CardCondition
    engine = ScoringEngine()
    high_conf = CardCondition(5,5,5,5,5,1.0)
    low_conf  = CardCondition(5,5,5,5,5,0.0)
    lo_h, hi_h = engine.compute_value_range(100.0, high_conf)
    lo_l, hi_l = engine.compute_value_range(100.0, low_conf)
    assert hi_h - lo_h < hi_l - lo_l  # low confidence → wider band


if __name__ == "__main__":
    test_normalize_strips_leading_zeros()
    test_cardmarket_trend_preferred()
    test_cardmarket_avg_fallback()
    test_holo_trend_preferred_over_regular_trend()
    test_tcgplayer_fallback_when_no_cardmarket()
    test_fetch_prices_tcgdex_only()
    test_fetch_prices_no_pricing_block_gives_zero()
    test_extract_language_specific_price_fr()
    test_extract_language_specific_price_missing()
    test_extract_graded_prices_from_ebay()
    test_extract_graded_prices_empty()
    test_score_to_grade_tier_mapping()
    test_value_range_widens_with_low_confidence()
    print("All tests passed.")
