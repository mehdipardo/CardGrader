# CardGrader

An AI-powered web app for Pokémon TCG collectors: scan a card, get an AI grading (centering, corners, edges, surface), fetch current CardMarket prices, and generate sale listings for Vinted, eBay, LeBonCoin and more.

## Quick start

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY (required) and RAPIDAPI_KEY (optional)
pip install -r requirements.txt
./run.sh                      # macOS / Linux
run.bat                       # Windows
```

Open **http://localhost:3000** in your browser.

## Architecture

```
Frontend  (http://localhost:3000)   React SPA in frontend/index.html
    │
    │  REST API calls
    ▼
Backend   (http://localhost:8000)   FastAPI in src/api.py
    │
    ├─ POST /api/identify    → Claude Vision — card identification
    ├─ POST /api/search      → TCGdex API   — find card versions
    ├─ POST /api/auto_match  → TCGdex       — best match disambiguation
    ├─ GET  /api/card/{id}   → TCGdex       — full card data + pricing
    ├─ POST /api/grade       → Claude Vision — physical condition grading
    ├─ POST /api/report      → full pipeline (identify + grade + price + score)
    └─ POST /api/listing     → Claude       — AI-generated sale listing
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key (card identification, grading, listings) |
| `RAPIDAPI_KEY` | ⬜ | RapidAPI key for enhanced pricing (falls back to TCGdex prices) |

## Scanner flow

1. **Upload** — Take a photo or import an image (front required, back optional).
2. **Identify** — Claude Vision reads the card name, number, language, and set.
3. **Select** — Choose the exact version from a grid of real TCGdex card images; the AI suggestion is highlighted automatically.
4. **Report** — Full grading report with sub-scores (centering/corners/edges/surface), price estimation, and confidence.
5. **Sell** — Generate an optimised listing for Vinted, eBay, LeBonCoin, FB Marketplace, or CardMarket with one click.

## Alternative: Streamlit app (fallback)

```bash
streamlit run app.py
```

## Project structure

```
frontend/
  index.html              # React SPA (self-contained, no build step)
src/
  api.py                  # FastAPI backend
  agents/identifier.py    # Vision agent — card identification
  agents/listing_generator.py  # AI listing generation
  tools/card_lookup.py    # TCGdex API — resolve card + set
  tools/pricing.py        # Pricing — CardMarket via TCGdex
  evaluation/grader.py    # Vision agent — physical condition grading
  evaluation/scoring.py   # Scoring engine — valuation calculation
  models/card.py          # Dataclasses: CardIdentity, CardCondition, CardPricing, CardReport
  orchestrator.py         # End-to-end pipeline coordinator
tests/                    # Unit tests
data/                     # Sample card images
database/schema.sql       # Supabase schema (PostgreSQL)
run.sh                    # Launch script (macOS/Linux)
run.bat                   # Launch script (Windows)
```
