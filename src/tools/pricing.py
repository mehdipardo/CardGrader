"""Tool for fetching Pokémon TCG card market prices."""

from src.models.card import CardIdentity, CardPricing


class PricingTool:
    """Retrieves current market prices for a card across grading tiers.

    Calls the PokemonPriceTracker API (or a compatible source such as
    TCGPlayer / CardMarket) to obtain raw and graded price points for a
    given card identity.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the tool with a pricing API key.

        Args:
            api_key: API key for the pricing data provider.
        """
        self.api_key = api_key

    def fetch_prices(self, identity: CardIdentity) -> CardPricing:
        """Fetch all available price tiers for a card.

        Uses the card's set_code and collector number to look up prices.
        Returns raw (ungraded) price as well as graded prices for standard
        PSA tiers (3, 5, 7, 9, 10) where available.

        Args:
            identity: A fully resolved CardIdentity (set_code must be set).

        Returns:
            A CardPricing object with all available price points filled in.

        Raises:
            ValueError: If identity.set_code is None.
            httpx.HTTPStatusError: On API request failures.
        """
        raise NotImplementedError

    def fetch_raw_price(self, identity: CardIdentity) -> float:
        """Fetch only the ungraded (raw) market price for quick lookups.

        Args:
            identity: A resolved CardIdentity.

        Returns:
            The current raw market price as a float.
        """
        raise NotImplementedError

    def _build_request_params(self, identity: CardIdentity) -> dict:
        """Build the query parameters required by the pricing API.

        Args:
            identity: The card identity to build params from.

        Returns:
            Dict of query parameters for the HTTP request.
        """
        raise NotImplementedError

    def _parse_pricing_response(self, response_data: dict) -> CardPricing:
        """Parse the raw API response into a CardPricing object.

        Maps API-specific field names to the standardised CardPricing fields.
        Handles missing grade tiers gracefully by setting them to None.

        Args:
            response_data: The JSON body returned by the pricing API.

        Returns:
            A populated CardPricing object.
        """
        raise NotImplementedError
