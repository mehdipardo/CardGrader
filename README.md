# CardGrader

An AI-powered agent that evaluates Pokémon TCG cards from a photo: it identifies the card, assesses its physical condition, fetches current market prices, and returns an estimated value — all in a single pipeline call.

## Workflow

1. **Capture** — Provide a photo of the card (JPEG/PNG/WEBP, front face).
2. **Identify** — `CardIdentifierAgent` sends the image to Claude Vision and extracts the card name, collector number, language, and set name.
3. **Resolve** — `CardLookupTool` queries the Pokémon TCG API to confirm the exact card record and retrieve the official set code and rarity.
4. **Grade** — `CardGrader` sends the image to Claude Vision again with a structured grading rubric and scores centering, corners, edges, and surface (each 1–10).
5. **Price** — `PricingTool` calls the pricing API to fetch the raw market price and graded prices for PSA tiers 3, 5, 7, 9, and 10.
6. **Score** — `ScoringEngine` maps the overall condition score to the nearest PSA tier, selects the matching price, and computes an estimated value with a confidence-weighted low/high range.
7. **Report** — The orchestrator assembles and returns a `CardReport` containing the full identity, condition breakdown, pricing data, estimated value, and overall pipeline confidence score.

## Quick start

```bash
cp .env.example .env          # fill in your API keys
pip install -r requirements.txt
python -c "
from dotenv import load_dotenv
load_dotenv()
from src.orchestrator import CardGraderOrchestrator
report = CardGraderOrchestrator.from_env().evaluate('data/my_card.jpg')
print(report)
"
```

## Project structure

```
src/
  agents/identifier.py      # Vision agent — card identification
  tools/card_lookup.py      # TCG API — resolve set code & rarity
  tools/pricing.py          # Pricing API — fetch market prices
  evaluation/grader.py      # Vision agent — physical condition grading
  evaluation/scoring.py     # Scoring engine — valuation calculation
  models/card.py            # Dataclasses: CardIdentity, CardCondition, CardPricing, CardReport
  orchestrator.py           # End-to-end pipeline coordinator
tests/                      # Unit and integration tests
data/                       # Sample card images for testing
```
