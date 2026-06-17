"""CardGrader FastAPI backend — exposes the grading pipeline as a REST API."""

import base64
import os
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from src.auth import get_current_user

load_dotenv()

app = FastAPI(title="CardGrader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")
    return key


def _save_upload(file: UploadFile) -> str:
    """Save an uploaded file to a temp path and return the path."""
    suffix = Path(file.filename or "image.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.flush()
    return tmp.name


def _save_b64(b64: str, suffix: str = ".jpg") -> str:
    """Decode a base64 string to a temp file and return the path."""
    data = base64.b64decode(b64)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.flush()
    return tmp.name


def _unlink(*paths: Optional[str]) -> None:
    for p in paths:
        if p:
            try:
                os.unlink(p)
            except OSError:
                pass


# ── POST /api/identify ─────────────────────────────────────────────────────

@app.post("/api/identify")
async def identify(front: UploadFile = File(...)):
    """Run Claude vision on the front image and return CardIdentity JSON."""
    from src.agents.identifier import CardIdentifierAgent

    front_path = _save_upload(front)
    try:
        agent    = CardIdentifierAgent(api_key=_api_key())
        identity = agent.identify(front_image_path=front_path)
    finally:
        _unlink(front_path)

    return {
        "name":     identity.name,
        "number":   identity.number,
        "language": identity.language,
        "set_name": identity.set_name or None,
        "set_code": identity.set_code,
        "rarity":   identity.rarity,
    }


# ── POST /api/search ───────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    name: str
    language: str = "FR"


TCGDEX_LANG: dict[str, str] = {
    "FR": "fr", "EN": "en", "JP": "ja", "DE": "de",
    "IT": "it", "ES": "es", "KO": "ko", "PT": "pt",
}

@app.post("/api/search")
async def search_cards(body: SearchRequest):
    """Search TCGdex by Pokémon name; return list of card stubs with images."""
    import httpx

    lang = TCGDEX_LANG.get(body.language.upper(), "en")
    try:
        resp = httpx.get(
            f"https://api.tcgdex.net/v2/{lang}/cards",
            params={"name": body.name},
            timeout=10.0,
        )
        resp.raise_for_status()
        candidates = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"TCGdex error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not isinstance(candidates, list):
        return {"candidates": [], "lang": lang}

    # Compute auto-match suggestion
    from src.tools.card_lookup import _number_matches, _extract_set_total

    # We don't have the original number here — clients pass it separately via
    # the number field in the identify response. Return raw stubs; the client
    # or /api/auto_match can disambiguate.
    return {"candidates": candidates, "lang": lang}


# ── POST /api/auto_match ───────────────────────────────────────────────────

class AutoMatchRequest(BaseModel):
    candidates: list
    number:    str
    lang:      str = "fr"
    set_name:  Optional[str] = None
    set_code:  Optional[str] = None


def _set_name_score(vision_set: str, card_set_name: str, card_set_id: str) -> int:
    """Return a match score (higher = better) between vision set hint and TCGdex set."""
    v = vision_set.lower()
    n = card_set_name.lower()
    i = card_set_id.lower()
    if v == n or v == i:
        return 3
    # All significant words from vision_set appear in card set name/id
    words = [w for w in v.split() if len(w) > 2]
    if words and all(w in n or w in i for w in words):
        return 2
    # At least one word matches
    if any(w in n or w in i for w in words):
        return 1
    return 0


@app.post("/api/auto_match")
async def auto_match(body: AutoMatchRequest):
    """Given search stubs + the vision number, return the best matching card id."""
    import httpx
    from src.tools.card_lookup import _number_matches, _extract_set_total

    candidates   = body.candidates
    number       = body.number
    lang         = body.lang
    total_in_set = _extract_set_total(number)

    local_matches = [
        c for c in candidates
        if _number_matches(number, str(c.get("localId") or c.get("id", "")))
    ]

    if not local_matches:
        return {"match_id": None}

    if len(local_matches) == 1:
        return {"match_id": local_matches[0]["id"]}

    # Multiple matches — fetch full cards to disambiguate
    perfect = acceptable = set_match = None
    best_set_score = 0

    for stub in local_matches:
        cid = stub.get("id")
        try:
            resp = httpx.get(f"https://api.tcgdex.net/v2/{lang}/cards/{cid}", timeout=10.0)
            resp.raise_for_status()
            full = resp.json()
        except Exception:
            continue

        card_count   = (full.get("set") or {}).get("cardCount") or {}
        card_set_id  = (full.get("set") or {}).get("id", "")
        card_set_name = (full.get("set") or {}).get("name", "")

        # Priority 1: set total matches perfectly
        if total_in_set is not None:
            if card_count.get("official") == total_in_set:
                return {"match_id": cid}
            if card_count.get("total") == total_in_set and acceptable is None:
                acceptable = cid

        # Priority 2: set name / set_code hint from vision
        hint = body.set_name or body.set_code or ""
        if hint:
            score = _set_name_score(hint, card_set_name, card_set_id)
            if score > best_set_score:
                best_set_score = score
                set_match = cid

    if acceptable:
        return {"match_id": acceptable}
    if set_match and best_set_score > 0:
        return {"match_id": set_match}
    return {"match_id": local_matches[0]["id"]}


# ── GET /api/card/{card_id} ────────────────────────────────────────────────

@app.get("/api/card/{card_id}")
async def get_card(card_id: str, lang: str = "fr"):
    """Fetch a full TCGdex card record (includes pricing block)."""
    import httpx

    try:
        resp = httpx.get(
            f"https://api.tcgdex.net/v2/{lang}/cards/{card_id}",
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ── POST /api/grade ────────────────────────────────────────────────────────

@app.post("/api/grade")
async def grade(
    front: UploadFile = File(...),
    back:  Optional[UploadFile] = File(None),
):
    """Grade card physical condition from images; return CardCondition JSON."""
    from src.evaluation.grader import CardGrader

    front_path = _save_upload(front)
    back_path  = _save_upload(back) if back and back.filename else None
    try:
        grader    = CardGrader(api_key=_api_key())
        condition = grader.grade(front_image_path=front_path, back_image_path=back_path)
    finally:
        _unlink(front_path, back_path)

    return {
        "centering":     condition.centering,
        "corners":       condition.corners,
        "edges":         condition.edges,
        "surface":       condition.surface,
        "overall_score": condition.overall_score,
        "confidence":    condition.confidence,
    }


# ── POST /api/report ───────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    card_id:     str
    lang:        str = "fr"
    front_image: str          # base64
    back_image:  Optional[str] = None  # base64


@app.post("/api/report")
async def full_report(body: ReportRequest):
    """Run the complete pipeline (grade + price + score) for a selected card."""
    import httpx
    from src.agents.identifier import CardIdentifierAgent
    from src.evaluation.grader import CardGrader
    from src.evaluation.scoring import ScoringEngine
    from src.models.card import CardIdentity
    from src.tools.pricing import PricingTool

    # Fetch the full TCGdex card
    try:
        resp = httpx.get(
            f"https://api.tcgdex.net/v2/{body.lang}/cards/{body.card_id}",
            timeout=10.0,
        )
        resp.raise_for_status()
        tcgdex_card = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TCGdex fetch failed: {exc}")

    # Build CardIdentity from TCGdex data
    set_info = tcgdex_card.get("set") or {}
    identity = CardIdentity(
        name=tcgdex_card.get("name", ""),
        number=tcgdex_card.get("localId", ""),
        language=body.lang.upper(),
        set_name=set_info.get("name", ""),
        set_code=set_info.get("id", "").split("-")[0] or None,
        rarity=tcgdex_card.get("rarity"),
    )

    # Save images to temp files
    front_path = _save_b64(body.front_image)
    back_path  = _save_b64(body.back_image) if body.back_image else None

    try:
        # Grade
        condition = CardGrader(api_key=_api_key()).grade(
            front_image_path=front_path,
            back_image_path=back_path,
        )

        # Price
        rapidapi_key = os.environ.get("RAPIDAPI_KEY")
        pricing = PricingTool(rapidapi_key=rapidapi_key).fetch_prices(
            identity=identity,
            tcgdex_card=tcgdex_card,
        )

        # Score
        report = ScoringEngine().compute_report(
            identity=identity,
            condition=condition,
            pricing=pricing,
            front_image_path=front_path,
            back_image_path=back_path,
        )
    finally:
        _unlink(front_path, back_path)

    return {
        "identity": {
            "name":     identity.name,
            "number":   tcgdex_card.get("localId", ""),
            "language": identity.language,
            "set_name": identity.set_name,
            "set_code": identity.set_code,
            "rarity":   identity.rarity,
            "image":    tcgdex_card.get("image", ""),
        },
        "condition": {
            "centering":     condition.centering,
            "corners":       condition.corners,
            "edges":         condition.edges,
            "surface":       condition.surface,
            "overall_score": condition.overall_score,
            "confidence":    condition.confidence,
        },
        "pricing": {
            "raw_price":         pricing.raw_price,
            "currency":          pricing.currency,
            "grade_10":          pricing.grade_10,
            "grade_9":           pricing.grade_9,
            "grade_7":           pricing.grade_7,
            "grade_5":           pricing.grade_5,
            "grade_3":           pricing.grade_3,
            "cardmarket_trend":  pricing.cardmarket_trend,
            "source_detail":     pricing.source_detail,
            "language_specific": pricing.language_specific,
        },
        "valuation": {
            "estimated_value":  report.estimated_value,
            "value_range_low":  report.value_range_low,
            "value_range_high": report.value_range_high,
            "confidence_score": report.confidence_score,
        },
    }


# ── POST /api/listing ──────────────────────────────────────────────────────

class ListingRequest(BaseModel):
    report:   dict
    platform: str
    language: str = "fr"


# ── POST /api/auth/register ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    pseudo:   str
    email:    str
    password: str


@app.post("/api/auth/register")
async def register(body: RegisterRequest):
    from src.auth import hash_password, create_token, supabase_client

    pseudo = body.pseudo.strip()
    email  = body.email.strip().lower()

    if len(pseudo) < 3:
        raise HTTPException(400, "Le pseudo doit contenir au moins 3 caractères")
    if len(body.password) < 6:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 6 caractères")
    if not email or "@" not in email:
        raise HTTPException(400, "Adresse email invalide")

    db = supabase_client()

    existing = db.table("users").select("id").eq("pseudo", pseudo).execute()
    if existing.data:
        raise HTTPException(409, "Ce pseudo est déjà pris")

    existing_email = db.table("users").select("id").eq("email", email).execute()
    if existing_email.data:
        raise HTTPException(409, "Cet email est déjà utilisé")

    result = db.table("users").insert({
        "pseudo":        pseudo,
        "email":         email,
        "password_hash": hash_password(body.password),
    }).execute()

    if not result.data:
        raise HTTPException(500, "Erreur lors de la création du compte")

    user = result.data[0]
    return {
        "token":  create_token(user["id"], user["pseudo"]),
        "pseudo": user["pseudo"],
        "id":     user["id"],
    }


# ── POST /api/auth/login ───────────────────────────────────────────────────

class LoginRequest(BaseModel):
    pseudo:   str
    password: str


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    from src.auth import verify_password, create_token, supabase_client

    db     = supabase_client()
    result = db.table("users").select("*").eq("pseudo", body.pseudo.strip()).execute()

    if not result.data or not verify_password(body.password, result.data[0]["password_hash"]):
        raise HTTPException(401, "Pseudo ou mot de passe incorrect")

    user = result.data[0]
    return {
        "token":  create_token(user["id"], user["pseudo"]),
        "pseudo": user["pseudo"],
        "id":     user["id"],
    }


# ── GET /api/auth/me ───────────────────────────────────────────────────────

@app.get("/api/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"pseudo": current_user["pseudo"], "id": current_user["sub"]}


# ── GET /api/collection (user) ─────────────────────────────────────────────

@app.get("/api/collection")
async def get_user_collection(current_user: dict = Depends(get_current_user)):
    from src.auth import supabase_client

    db     = supabase_client()
    result = db.table("collection") \
               .select("*") \
               .eq("user_id", current_user["sub"]) \
               .order("added_at") \
               .execute()
    return {"items": result.data or []}


# ── POST /api/collection ───────────────────────────────────────────────────

class CollectionAddRequest(BaseModel):
    report: dict


@app.post("/api/collection")
async def add_collection_item(body: CollectionAddRequest, current_user: dict = Depends(get_current_user)):
    from src.auth import supabase_client

    db     = supabase_client()
    result = db.table("collection").insert({
        "user_id": current_user["sub"],
        "report":  body.report,
    }).execute()

    if not result.data:
        raise HTTPException(500, "Erreur lors de l'ajout à la collection")
    return result.data[0]


# ── DELETE /api/collection/{item_id} ──────────────────────────────────────

@app.delete("/api/collection/{item_id}")
async def delete_collection_item(item_id: str, current_user: dict = Depends(get_current_user)):
    from src.auth import supabase_client

    db = supabase_client()
    db.table("collection") \
      .delete() \
      .eq("id", item_id) \
      .eq("user_id", current_user["sub"]) \
      .execute()
    return {"ok": True}


# ── POST /api/listing ──────────────────────────────────────────────────────

@app.post("/api/listing")
async def generate_listing(body: ListingRequest):
    """Generate an optimised sale listing for the given platform."""
    from src.agents.listing_generator import ListingGenerator
    from src.models.card import (
        CardCondition, CardIdentity, CardPricing, CardReport,
    )
    from datetime import datetime

    r = body.report
    try:
        identity = CardIdentity(
            name=r["identity"]["name"],
            number=r["identity"]["number"],
            language=r["identity"]["language"],
            set_name=r["identity"].get("set_name") or "",
            set_code=r["identity"].get("set_code"),
            rarity=r["identity"].get("rarity"),
        )
        condition = CardCondition(
            centering=r["condition"]["centering"],
            corners=r["condition"]["corners"],
            edges=r["condition"]["edges"],
            surface=r["condition"]["surface"],
            overall_score=r["condition"]["overall_score"],
            confidence=r["condition"]["confidence"],
        )
        p = r["pricing"]
        pricing = CardPricing(
            raw_price=p["raw_price"],
            currency=p.get("currency", "EUR"),
            grade_10=p.get("grade_10"),
            grade_9=p.get("grade_9"),
            grade_7=p.get("grade_7"),
            grade_5=p.get("grade_5"),
            grade_3=p.get("grade_3"),
            source="api",
            last_updated=datetime.utcnow(),
            source_detail=p.get("source_detail", ""),
            language_specific=p.get("language_specific", False),
            cardmarket_trend=p.get("cardmarket_trend"),
            tcgplayer_market=p.get("tcgplayer_market"),
        )
        v = r["valuation"]
        report = CardReport(
            identity=identity,
            condition=condition,
            pricing=pricing,
            estimated_value=v["estimated_value"],
            value_range_low=v["value_range_low"],
            value_range_high=v["value_range_high"],
            confidence_score=v["confidence_score"],
        )
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid report structure: {exc}")

    try:
        listing = ListingGenerator(api_key=_api_key()).generate(
            report, body.platform, body.language
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return listing
