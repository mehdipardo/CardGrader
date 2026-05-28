"""Tool for resolving a card's exact API record from identity fields."""

from src.models.card import CardIdentity


class CardLookupTool:
    """Queries the Pokémon TCG API to resolve a canonical card record.

    Takes the fields extracted by CardIdentifierAgent (name, number, language,
    set) and returns a normalised card record including the official set code
    and rarity, which are needed for accurate pricing lookups.
    """

    BASE_URL = "https://api.pokemontcg.io/v2"

    def __init__(self, api_key: str) -> None:
        """Initialise the tool with a Pokémon TCG API key.

        Args:
            api_key: API key for pokemontcg.io authentication.
        """
        self.api_key = api_key

    def lookup(self, identity: CardIdentity) -> CardIdentity:
        """Enrich a CardIdentity with official set code and rarity.

        Queries the TCG API using the card number and set name, then
        returns a new CardIdentity with set_code and rarity filled in.

        Args:
            identity: Partially filled CardIdentity from the vision agent.

        Returns:
            An enriched CardIdentity with set_code and rarity populated.

        Raises:
            LookupError: If no matching card is found in the API.
            httpx.HTTPStatusError: On API request failures.
        """
        raise NotImplementedError

    def search_by_number_and_set(self, number: str, set_name: str, language: str) -> dict:
        """Send a search query to the TCG API and return the raw result.

        Builds a query string (e.g. `number:4 set.name:"Base Set"`) and
        fetches matching cards. Handles pagination if necessary.

        Args:
            number: Collector number (e.g. "4/102" or just "4").
            set_name: Full or partial set name.
            language: Card language — used to select the correct API endpoint
                for non-English cards.

        Returns:
            The first matching card data dict from the API response.

        Raises:
            LookupError: If no results are returned.
        """
        raise NotImplementedError

    def _build_headers(self) -> dict:
        """Return HTTP headers including the API key.

        Returns:
            Dict of request headers.
        """
        raise NotImplementedError
