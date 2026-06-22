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
    number: Optional[str] = None  # Used to prioritise JA↔FR conversion by localId


TCGDEX_LANG: dict[str, str] = {
    "FR": "fr", "EN": "en", "JP": "ja", "DE": "de",
    "IT": "it", "ES": "es", "KO": "ko", "PT": "pt",
}

# Katakana → English name map for Gen 1 (original Japanese cards have
# different numbering than EN sets, so we must search EN by translated name
# to surface Base Set / early set cards that TCGdex indexes under EN IDs).
JP_TO_EN: dict[str, str] = {
    "フシギダネ": "Bulbasaur",   "フシギソウ": "Ivysaur",      "フシギバナ": "Venusaur",
    "ヒトカゲ":  "Charmander",   "リザード":   "Charmeleon",    "リザードン": "Charizard",
    "ゼニガメ":  "Squirtle",     "カメール":   "Wartortle",     "カメックス": "Blastoise",
    "キャタピー": "Caterpie",    "トランセル": "Metapod",       "バタフリー": "Butterfree",
    "ビードル":  "Weedle",       "コクーン":   "Kakuna",        "スピアー":   "Beedrill",
    "ポッポ":    "Pidgey",       "ピジョン":   "Pidgeotto",     "ピジョット": "Pidgeot",
    "コラッタ":  "Rattata",      "ラッタ":     "Raticate",      "オニスズメ": "Spearow",
    "オニドリル": "Fearow",      "アーボ":     "Ekans",         "アーボック": "Arbok",
    "ピカチュウ": "Pikachu",     "ライチュウ": "Raichu",        "サンド":     "Sandshrew",
    "サンドパン": "Sandslash",   "ニドリーナ": "Nidorina",      "ニドクイン": "Nidoqueen",
    "ニドリーノ": "Nidorino",    "ニドキング": "Nidoking",      "ピッピ":     "Clefairy",
    "ピクシー":  "Clefable",     "ロコン":     "Vulpix",        "キュウコン": "Ninetales",
    "プリン":    "Jigglypuff",   "プクリン":   "Wigglytuff",    "ズバット":   "Zubat",
    "ゴルバット": "Golbat",      "ナゾノクサ": "Oddish",        "クサイハナ": "Gloom",
    "ラフレシア": "Vileplume",   "パラス":     "Paras",         "パラセクト": "Parasect",
    "コンパン":  "Venonat",      "モルフォン": "Venomoth",      "ディグダ":   "Diglett",
    "ダグトリオ": "Dugtrio",     "ニャース":   "Meowth",        "ペルシアン": "Persian",
    "コダック":  "Psyduck",      "ゴルダック": "Golduck",       "マンキー":   "Mankey",
    "オコリザル": "Primeape",    "ガーディ":   "Growlithe",     "ウインディ": "Arcanine",
    "ニョロモ":  "Poliwag",      "ニョロゾ":   "Poliwhirl",     "ニョロボン": "Poliwrath",
    "ケーシィ":  "Abra",         "ユンゲラー": "Kadabra",       "フーディン": "Alakazam",
    "マッチョ":  "Machop",       "ゴーリキー": "Machoke",       "カイリキー": "Machamp",
    "マダツボミ": "Bellsprout",  "ウツドン":   "Weepinbell",    "ウツボット": "Victreebel",
    "メノクラゲ": "Tentacool",   "ドククラゲ": "Tentacruel",    "イシツブテ": "Geodude",
    "ゴローン":  "Graveler",     "ゴローニャ": "Golem",         "ポニータ":   "Ponyta",
    "ギャロップ": "Rapidash",    "ヤドン":     "Slowpoke",      "ヤドラン":   "Slowbro",
    "コイル":    "Magnemite",    "レアコイル": "Magneton",      "カモネギ":   "Farfetch'd",
    "ドードー":  "Doduo",        "ドードリオ": "Dodrio",        "パウワウ":   "Seel",
    "ジュゴン":  "Dewgong",      "ベトベター": "Grimer",        "ベトベトン": "Muk",
    "シェルダー": "Shellder",    "パルシェン": "Cloyster",      "ゴース":     "Gastly",
    "ゴースト":  "Haunter",      "ゲンガー":   "Gengar",        "イワーク":   "Onix",
    "スリープ":  "Drowzee",      "スリーパー": "Hypno",         "クラブ":     "Krabby",
    "キングラー": "Kingler",     "ビリリダマ": "Voltorb",       "マルマイン": "Electrode",
    "タマタマ":  "Exeggcute",    "ナッシー":   "Exeggutor",     "カラカラ":   "Cubone",
    "ガラガラ":  "Marowak",      "サワムラー": "Hitmonlee",     "エビワラー": "Hitmonchan",
    "ベロリンガ": "Lickitung",   "ドガース":   "Koffing",       "マタドガス": "Weezing",
    "サイホーン": "Rhyhorn",     "サイドン":   "Rhydon",        "ラッキー":   "Chansey",
    "モンジャラ": "Tangela",     "ガルーラ":   "Kangaskhan",    "タッツー":   "Horsea",
    "シードラ":  "Seadra",       "トサキント": "Goldeen",       "アズマオウ": "Seaking",
    "ヒトデマン": "Staryu",      "スターミー": "Starmie",       "バリヤード": "Mr. Mime",
    "ストライク": "Scyther",     "ルージュラ": "Jynx",          "エレブー":   "Electabuzz",
    "ブーバー":  "Magmar",       "カイロス":   "Pinsir",        "ケンタロス": "Tauros",
    "コイキング": "Magikarp",    "ギャラドス": "Gyarados",      "ラプラス":   "Lapras",
    "メタモン":  "Ditto",        "イーブイ":   "Eevee",         "シャワーズ": "Vaporeon",
    "サンダース": "Jolteon",     "ブースター": "Flareon",       "ポリゴン":   "Porygon",
    "オムナイト": "Omanyte",     "オムスター": "Omastar",       "カブト":     "Kabuto",
    "カブトプス": "Kabutops",    "プテラ":     "Aerodactyl",    "カビゴン":   "Snorlax",
    "フリーザー": "Articuno",    "サンダー":   "Zapdos",        "ファイヤー": "Moltres",
    "ミニリュウ": "Dratini",     "ハクリュー": "Dragonair",     "カイリュー": "Dragonite",
    "ミュウツー": "Mewtwo",      "ミュウ":     "Mew",
}

@app.post("/api/search")
async def search_cards(body: SearchRequest):
    """Search TCGdex by Pokémon name; return list of card stubs with images."""
    import httpx

    primary_lang = TCGDEX_LANG.get(body.language.upper(), "en")

    def _fetch_cards(lang: str, name: str) -> list:
        try:
            r = httpx.get(
                f"https://api.tcgdex.net/v2/{lang}/cards",
                params={"name": name},
                timeout=10.0,
            )
            r.raise_for_status()
            result = r.json()
            return result if isinstance(result, list) else []
        except Exception:
            return []

    candidates   = _fetch_cards(primary_lang, body.name)
    active_lang  = primary_lang

    # For non-FR/EN languages with few results, fall back to FR then EN.
    # Old Japanese cards are only indexed by their Japanese name in the JA endpoint;
    # searching "Aspicot" finds nothing there for the 1996 Base Set, but the FR
    # endpoint has those cards.  Once we find a FR card (e.g. base1-013) we then
    # try to fetch the JA version at the same ID — TCGdex uses consistent card IDs
    # across languages — so the user gets the Japanese version when available.
    if len(candidates) < 3 and primary_lang not in ("fr", "en"):
        from src.tools.card_lookup import _number_matches as _nm
        for fb_lang in ("fr", "en"):
            fb_cards = _fetch_cards(fb_lang, body.name)
            if not fb_cards:
                continue
            existing_ids = {c.get("id") for c in candidates}
            new_cards    = [c for c in fb_cards if c.get("id") not in existing_ids]
            if not new_cards:
                continue

            # For JA primary: try to get the JA version of each new FR card.
            # Prioritise cards whose localId matches the vision number hint.
            if primary_lang == "ja":
                num      = body.number or ""
                priority = ([c for c in new_cards if _nm(num, str(c.get("localId") or ""))]
                            if num else new_cards[:5])
                rest     = ([c for c in new_cards if not _nm(num, str(c.get("localId") or ""))]
                            if num else new_cards[5:])

                ja_converted: list = []
                for fb_card in priority[:5]:
                    cid = fb_card.get("id", "")
                    try:
                        r = httpx.get(
                            f"https://api.tcgdex.net/v2/ja/cards/{cid}", timeout=5.0
                        )
                        if r.status_code == 200:
                            ja_data = r.json()
                            ja_converted.append({
                                "id":      cid,
                                "localId": ja_data.get("localId") or fb_card.get("localId"),
                                "name":    ja_data.get("name")    or fb_card.get("name"),
                                "image":   ja_data.get("image")   or fb_card.get("image"),
                            })
                        else:
                            ja_converted.append(fb_card)  # Keep FR stub as fallback
                    except Exception:
                        ja_converted.append(fb_card)

                new_cards   = ja_converted + rest
                active_lang = primary_lang  # Stay JA; JA-converted cards use JA data
            else:
                active_lang = fb_lang

            candidates = candidates + new_cards
            break

    # For JP cards: the original Japanese sets (Base Set, Jungle, etc.) use different
    # card numbering from EN sets (JP Blastoise = 009, EN Blastoise = 2/102).
    # TCGdex primarily indexes these cards under EN IDs. So we also search EN using
    # the translated English name, then try to fetch the JA version of each result.
    # This makes vintage JP Base Set cards discoverable alongside modern JA cards.
    if primary_lang == "ja":
        from src.tools.card_lookup import _number_matches as _nm
        en_name = JP_TO_EN.get(body.name)
        if en_name:
            en_cards = _fetch_cards("en", en_name)
            if en_cards:
                existing_ids = {c.get("id") for c in candidates}
                new_en = [c for c in en_cards if c.get("id") not in existing_ids]
                # For JP vintage cards, sort vintage sets first so they survive the [:12] cap.
                # Without this, modern SV2a/XY cards dominate the first 12 results and
                # base1/jungle/etc. Blastoise cards never make it into candidates.
                _VINTAGE_SET_IDS = {
                    "base1","jungle","fossil","gym1","gym2","base2","neo1","neo2","neo3","neo4"
                }
                jp_is_old = body.number and "/" not in body.number and body.number.lstrip("0").isdigit()
                if jp_is_old:
                    new_en = (
                        [c for c in new_en if c.get("id","").split("-")[0] in _VINTAGE_SET_IDS] +
                        [c for c in new_en if c.get("id","").split("-")[0] not in _VINTAGE_SET_IDS]
                    )
                # Try to fetch JA version of each EN card (TCGdex shares card IDs
                # across languages for cards that exist in both). Fall back to EN stub.
                # For old JP format numbers (e.g. "009"), strip leading zeros to get
                # the JP localId ("9"). Original JP sets use JP numbering as localId,
                # which differs from EN localId (JP Blastoise=9, EN Blastoise=2).
                jp_num = body.number.lstrip("0") if body.number and "/" not in body.number else None

                ja_from_en: list = []
                for en_card in new_en[:12]:  # cap to avoid excessive requests
                    cid = en_card.get("id", "")
                    set_id = cid.split("-")[0] if "-" in cid else ""
                    ja_found = False

                    # Strategy 1: try same card ID (works for modern sets that share IDs)
                    try:
                        r = httpx.get(
                            f"https://api.tcgdex.net/v2/ja/cards/{cid}", timeout=5.0
                        )
                        if r.status_code == 200:
                            ja_data = r.json()
                            ja_from_en.append({
                                "id":      cid,
                                "localId": ja_data.get("localId") or en_card.get("localId"),
                                "name":    ja_data.get("name")    or en_card.get("name"),
                                "image":   ja_data.get("image")   or en_card.get("image"),
                            })
                            ja_found = True
                    except Exception:
                        pass

                    # Strategy 2 (vintage JP sets only): try set_id + JP number as localId
                    # e.g. base1-9 for カメックス 009 instead of base1-2 (EN number)
                    if not ja_found and jp_num and set_id:
                        jp_card_id = f"{set_id}-{jp_num}"
                        try:
                            r2 = httpx.get(
                                f"https://api.tcgdex.net/v2/ja/cards/{jp_card_id}", timeout=5.0
                            )
                            if r2.status_code == 200:
                                ja_data = r2.json()
                                ja_from_en.append({
                                    "id":      jp_card_id,
                                    "localId": ja_data.get("localId") or jp_num,
                                    "name":    ja_data.get("name")    or en_card.get("name"),
                                    "image":   ja_data.get("image")   or en_card.get("image"),
                                })
                                ja_found = True
                        except Exception:
                            pass

                    if not ja_found:
                        # TCGdex doesn't have the original 1996 JP sets.
                        # Mark EN stub so frontend can explain the situation to user.
                        en_card["_jp_en_fallback"] = True
                        ja_from_en.append(en_card)

                candidates = candidates + ja_from_en
                if not active_lang or active_lang == "ja":
                    active_lang = "en"  # use EN for set name enrichment

    # If still empty, strip common trainer-type prefixes Vision sometimes prepends
    # (e.g. "Dresseur - Détermination d'Ondine" → "Détermination d'Ondine")
    if not candidates:
        import re
        TRAINER_PREFIXES = re.compile(
            r"^(Dresseur|Supporter|Objet|Stade|Outil(?:\s+Pokémon)?|"
            r"Trainer|Item|Stadium|Tool|Pokémon\s+Tool)\s*[-–]\s*",
            re.IGNORECASE,
        )
        stripped = TRAINER_PREFIXES.sub("", body.name).strip()
        if stripped and stripped.lower() != body.name.lower():
            for try_lang in (primary_lang, "fr", "en"):
                candidates = _fetch_cards(try_lang, stripped)
                if candidates:
                    active_lang = try_lang
                    break

    if not candidates:
        return {"candidates": [], "lang": active_lang}

    # Fetch set list to enrich stubs with human-readable set name.
    # TCGdex search stubs only carry {id, localId, name, image} — no set info.
    # The card id format is "{setId}-{localId}", so we parse setId then look it up.
    try:
        sets_resp = httpx.get(f"https://api.tcgdex.net/v2/{active_lang}/sets", timeout=10.0)
        sets_resp.raise_for_status()
        set_map: dict[str, str] = {
            s["id"]: s.get("name", s["id"])
            for s in sets_resp.json()
            if isinstance(s, dict) and "id" in s
        }
    except Exception:
        set_map = {}

    for c in candidates:
        card_id = c.get("id", "")
        set_id  = card_id.split("-")[0] if "-" in card_id else ""
        if set_id:
            c["set"] = {"id": set_id, "name": set_map.get(set_id, set_id)}

    return {"candidates": candidates, "lang": active_lang}


# ── POST /api/auto_match ───────────────────────────────────────────────────

class AutoMatchRequest(BaseModel):
    candidates: list
    number:    str
    lang:      str = "fr"
    set_name:  Optional[str] = None
    set_code:  Optional[str] = None
    original_lang: Optional[str] = None  # scan language, may differ from search lang


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

    # For old Japanese cards the number format is "009" (zero-padded, no /total)
    # and the EN localId is completely different (JP 009 = EN 2 for Base Blastoise).
    # When no local match is found and the number looks like a vintage JP number,
    # fall back to set-name scoring across all candidates.
    # Use original_lang (the scan language) rather than lang (the TCGdex search lang),
    # because the search may switch to "en" when falling back to EN card data, which
    # would otherwise hide the JP vintage scoring path.
    detect_lang = (body.original_lang or lang or "").lower()
    jp_old_number = (
        detect_lang in ("ja", "jp")  # "jp" = raw scan identity lang, "ja" = TCGdex lang code
        and "/" not in number
        and number.lstrip("0").isdigit()
    )

    if not local_matches and not jp_old_number:
        return {"match_id": None}

    scored_candidates = local_matches if local_matches else candidates

    if len(scored_candidates) == 1:
        return {"match_id": scored_candidates[0]["id"]}

    # Multiple matches — fetch full cards to disambiguate
    perfect = acceptable = set_match = None
    best_set_score = 0

    for stub in scored_candidates:
        cid = stub.get("id")
        full = None
        # For JP searches, try JA first (vintage JP cards may only exist in JA endpoint)
        langs_to_try = (["ja", lang] if lang == "ja" or body.lang == "ja" else [lang])
        for try_lang in langs_to_try:
            try:
                resp = httpx.get(f"https://api.tcgdex.net/v2/{try_lang}/cards/{cid}", timeout=10.0)
                if resp.status_code == 200:
                    full = resp.json()
                    break
            except Exception:
                continue
        if not full:
            continue

        card_count   = (full.get("set") or {}).get("cardCount") or {}
        card_set_id  = (full.get("set") or {}).get("id", "")
        card_set_name = (full.get("set") or {}).get("name", "")

        # Priority 1: set total matches perfectly (not useful for JP old-format)
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

        # Priority 3 (JP old-format only): prefer earliest known vintage sets.
        # Ordered so base1 beats jungle beats fossil etc. — critical when a
        # Pokémon appears in multiple vintage sets (different JP numbers, same EN name).
        _VINTAGE_PRIORITY = {
            "base1": 14, "jungle": 13, "fossil": 12,
            "gym1": 11,  "gym2": 10,  "base2": 9,
            "neo1": 8,   "neo2": 7,   "neo3": 6,  "neo4": 5,
        }
        if jp_old_number and card_set_id in _VINTAGE_PRIORITY:
            prio = _VINTAGE_PRIORITY[card_set_id] + 4  # always beats set-name score (max 3)
            if prio > best_set_score:
                best_set_score = prio
                set_match = cid

    if acceptable:
        return {"match_id": acceptable}
    if set_match and best_set_score > 0:
        return {"match_id": set_match}
    return {"match_id": scored_candidates[0]["id"]}


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
    # Original vision identity from the scan. When the matched TCGdex card is in a
    # different language than the scanned card (e.g. JP vintage card matched to its
    # EN equivalent because TCGdex lacks usable JP vintage data), we preserve the
    # scanned identity for display so the user still sees "カメックス · 009 · JP".
    scan_identity: Optional[dict] = None


@app.post("/api/report")
async def full_report(body: ReportRequest):
    """Run the complete pipeline (grade + price + score) for a selected card."""
    import httpx
    from src.agents.identifier import CardIdentifierAgent
    from src.evaluation.grader import CardGrader
    from src.evaluation.scoring import ScoringEngine
    from src.models.card import CardIdentity
    from src.tools.pricing import PricingTool

    # Fetch the full TCGdex card.  Try the requested lang first; fall back to fr
    # then en so old Japanese-only sets (which may not exist in the JA endpoint
    # under a searchable name) can still produce a report.
    tcgdex_card = None
    lang_used   = body.lang
    for try_lang in (body.lang, "fr", "en"):
        try:
            resp = httpx.get(
                f"https://api.tcgdex.net/v2/{try_lang}/cards/{body.card_id}",
                timeout=10.0,
            )
            resp.raise_for_status()
            tcgdex_card = resp.json()
            lang_used   = try_lang
            break
        except Exception:
            pass
    if tcgdex_card is None:
        raise HTTPException(status_code=502, detail=f"TCGdex card '{body.card_id}' not found in any language")

    # Build CardIdentity from TCGdex data
    set_info = tcgdex_card.get("set") or {}
    identity = CardIdentity(
        name=tcgdex_card.get("name", ""),
        number=tcgdex_card.get("localId", ""),
        language=lang_used.upper(),
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

        # Price — Layer 3 (JustTCG) fires for JP cards when the key is present
        rapidapi_key  = os.environ.get("RAPIDAPI_KEY")
        justtcg_key   = os.environ.get("JUSTTCG_API_KEY")
        scan_lang     = ((body.scan_identity or {}).get("language") or "").upper() or None
        pricing = PricingTool(rapidapi_key=rapidapi_key, justtcg_key=justtcg_key).fetch_prices(
            identity=identity,
            tcgdex_card=tcgdex_card,
            scan_language=scan_lang,
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

    # Build the DISPLAYED identity. By default it mirrors the matched TCGdex card.
    # But when the scan was in a different language than the matched card (cross-language
    # fallback, e.g. JP card → EN equivalent), preserve the scanned name/number/language
    # so the report stays faithful to the physical card the user actually holds.
    # The image and pricing still come from the matched (EN) card.
    scan = body.scan_identity or {}
    scan_lang = (scan.get("language") or "").upper()
    cross_lang = bool(scan_lang and scan_lang != lang_used.upper())

    disp_name     = identity.name
    disp_number   = tcgdex_card.get("localId", "")
    disp_language = identity.language
    disp_set_name = identity.set_name
    equiv_lang    = None  # language of the card whose data (image/price) we used

    if cross_lang:
        disp_name     = scan.get("name")     or disp_name
        disp_number   = scan.get("number")   or disp_number
        disp_language = scan_lang
        disp_set_name = scan.get("set_name") or disp_set_name
        equiv_lang    = lang_used.upper()  # signal to frontend that data is from this lang

    return {
        "identity": {
            "name":     disp_name,
            "number":   disp_number,
            "language": disp_language,
            "set_name": disp_set_name,
            "set_code": identity.set_code,
            "rarity":   identity.rarity,
            "image":    tcgdex_card.get("image", ""),
            "equiv_lang": equiv_lang,
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
