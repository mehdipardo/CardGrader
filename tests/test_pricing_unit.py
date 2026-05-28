"""Unit tests for pricing helpers (no live API calls)."""

from src.tools.pricing import PricingTool


def test_match_card_by_number_variants() -> None:
    tool = PricingTool(api_key="test")
    cards = [
        {"number": "2/102", "prices": {"market": 45.5}},
        {"cardNumber": "2", "totalSetNumber": "102", "prices": {"market": 99.0}},
    ]
    match = tool._match_card_by_number(cards, "02/102")
    assert match is not None
    assert match["prices"]["market"] == 45.5


def test_ebay_price_parsing_and_median() -> None:
    tool = PricingTool(api_key="test")
    html = (
        '<span class="s-item__price">12,50 EUR</span>'
        '<span class="s-item__price">15,00 EUR</span>'
        '<span class="s-item__price">10,00 EUR</span>'
    )
    prices = tool._parse_ebay_prices(html)
    assert len(prices) == 3
    assert tool._median_of_recent_sales(prices) == 12.5
    assert tool._median_of_recent_sales(prices[:2]) is None


if __name__ == "__main__":
    test_match_card_by_number_variants()
    test_ebay_price_parsing_and_median()
    print("All pricing unit tests passed.")
