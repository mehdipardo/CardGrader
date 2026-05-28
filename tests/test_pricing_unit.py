"""Unit tests for PokeTrace pricing helpers (no live API calls)."""

from src.tools.pricing import (
    CardNotFoundError,
    PricingTool,
    _get_price,
    _normalize_number,
    _number_matches,
)


def test_normalize_number_strips_leading_zeros() -> None:
    assert _normalize_number("002/102") == "2/102"
    assert _normalize_number("026/106") == "26/106"
    assert _normalize_number("2/102")   == "2/102"
    assert _normalize_number("100/100") == "100/100"


def test_number_matches_zero_padding_tolerant() -> None:
    assert _number_matches("002/102", "2/102")
    assert _number_matches("2/102",   "2/102")
    assert _number_matches("026/106", "26/106")
    assert not _number_matches("3/102", "2/102")
    assert not _number_matches("2/102", "2/103")


def test_get_price_happy_path() -> None:
    prices = {
        "ebay":      {"NEAR_MINT": {"avg": 60.0}},
        "tcgplayer": {"NEAR_MINT": {"avg": 45.5}},
    }
    assert _get_price(prices, "ebay",      "NEAR_MINT") == 60.0
    assert _get_price(prices, "tcgplayer", "NEAR_MINT") == 45.5


def test_get_price_returns_none_on_missing_market() -> None:
    prices = {"tcgplayer": {"NEAR_MINT": {"avg": 45.5}}}
    assert _get_price(prices, "ebay", "NEAR_MINT") is None


def test_get_price_returns_none_on_missing_condition() -> None:
    prices = {"ebay": {"LIGHTLY_PLAYED": {"avg": 30.0}}}
    assert _get_price(prices, "ebay", "NEAR_MINT") is None


def test_get_price_returns_none_when_avg_is_null() -> None:
    prices = {"ebay": {"NEAR_MINT": {"avg": None}}}
    assert _get_price(prices, "ebay", "NEAR_MINT") is None


def test_parse_pricing_response_prefers_ebay() -> None:
    from src.models.card import CardIdentity
    tool = PricingTool(api_key="test")
    identity = CardIdentity(name="Blastoise", number="2/102", language="EN", set_name="")
    data = {
        "data": [{
            "name": "Blastoise",
            "cardNumber": "002/102",
            "prices": {
                "ebay":      {"NEAR_MINT": {"avg": 60.0}},
                "tcgplayer": {"NEAR_MINT": {"avg": 45.5}},
            },
        }]
    }
    pricing = tool._parse_pricing_response(data, identity)
    assert pricing.raw_price == 60.0
    assert pricing.source == "poketrace"
    assert pricing.currency == "USD"
    assert pricing.grade_10 is None


def test_parse_pricing_response_falls_back_to_tcgplayer() -> None:
    from src.models.card import CardIdentity
    tool = PricingTool(api_key="test")
    identity = CardIdentity(name="Blastoise", number="2/102", language="EN", set_name="")
    data = {
        "data": [{
            "name": "Blastoise",
            "cardNumber": "002/102",
            "prices": {"tcgplayer": {"NEAR_MINT": {"avg": 45.5}}},
        }]
    }
    pricing = tool._parse_pricing_response(data, identity)
    assert pricing.raw_price == 45.5


def test_parse_pricing_response_raises_on_no_match() -> None:
    from src.models.card import CardIdentity
    tool = PricingTool(api_key="test")
    identity = CardIdentity(name="Blastoise", number="2/102", language="EN", set_name="")
    data = {"data": [{"cardNumber": "4/102", "prices": {}}]}
    try:
        tool._parse_pricing_response(data, identity)
        assert False, "Should have raised CardNotFoundError"
    except CardNotFoundError:
        pass


if __name__ == "__main__":
    test_normalize_number_strips_leading_zeros()
    test_number_matches_zero_padding_tolerant()
    test_get_price_happy_path()
    test_get_price_returns_none_on_missing_market()
    test_get_price_returns_none_on_missing_condition()
    test_get_price_returns_none_when_avg_is_null()
    test_parse_pricing_response_prefers_ebay()
    test_parse_pricing_response_falls_back_to_tcgplayer()
    test_parse_pricing_response_raises_on_no_match()
    print("All pricing unit tests passed.")
