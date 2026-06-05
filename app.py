"""CardGrader — Multi-page Streamlit app for Pokémon TCG card analysis."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="CardGrader",
    page_icon="🎴",
    layout="wide",
    initial_sidebar_state="collapsed",
)

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────
LANGUAGE_FLAGS: dict[str, str] = {
    "FR": "🇫🇷", "EN": "🇬🇧", "JP": "🇯🇵",
    "DE": "🇩🇪", "IT": "🇮🇹", "ES": "🇪🇸",
    "KO": "🇰🇷", "PT": "🇧🇷",
}

PLATFORM_LABELS: dict[str, str] = {
    "vinted":     "Vinted",
    "ebay":       "eBay",
    "leboncoin":  "LeBonCoin",
    "facebook":   "Facebook Marketplace",
    "cardmarket": "CardMarket",
}

GITHUB_URL = "https://github.com/mehdipardo/CardGrader"


# ── Session state initialisation ───────────────────────────────────────────
def _init_state() -> None:
    defaults = {
        "page":                "accueil",
        "scan_history":        [],
        "collection":          [],
        "current_report":      None,
        # Scanner step-machine
        "step":                "upload",
        "id_pending":          None,   # CardIdentity from vision
        "tcgdex_candidates":   [],     # list of stubs from TCGdex search
        "auto_match_id":       None,   # card id that best matches the number
        "auto_match_card":     None,   # full card dict for the auto-match
        "selected_card":       None,   # full card dict chosen by user
        "show_all_cards":      False,  # toggle "Voir plus" in gallery
        "search_name":         None,   # manual name override for retry search
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

_init_state()


# ── API key guard ──────────────────────────────────────────────────────────
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    st.error(
        "❌ **ANTHROPIC_API_KEY manquante.** "
        "Ajoutez-la dans votre fichier `.env` ou variables d'environnement."
    )
    st.stop()


# ── Helpers ────────────────────────────────────────────────────────────────
def score_color(score: float) -> str:
    if score >= 8:
        return "🟢"
    if score >= 5:
        return "🟠"
    return "🔴"


def _ext(f) -> str:
    name = getattr(f, "name", "image.jpg")
    return Path(name).suffix or ".jpg"


def save_uploaded(file_like, suffix: str) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_like.read() if hasattr(file_like, "read") else file_like.getvalue())
    tmp.flush()
    return tmp.name


def _go(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def _report_to_entry(report, scanned_at: Optional[str] = None) -> dict:
    """Serialize a full CardReport into a flat session_state entry."""
    return {
        "card_name":        report.identity.name,
        "card_number":      report.identity.number,
        "language":         report.identity.language,
        "set_name":         report.identity.set_name or "",
        "rarity":           report.identity.rarity or "",
        "overall_score":    report.condition.overall_score,
        "estimated_value":  report.estimated_value,
        "value_range_low":  report.value_range_low,
        "value_range_high": report.value_range_high,
        "confidence":       report.confidence_score,
        "scanned_at":       scanned_at or datetime.utcnow().isoformat(),
        "report":           report,
        "_identity":        report.identity,
        "_condition":       report.condition,
    }


def _partial_entry(identity, condition, scanned_at: Optional[str] = None) -> dict:
    """Build a session_state entry from identity + condition only (no pricing/scoring)."""
    return {
        "card_name":        identity.name,
        "card_number":      identity.number,
        "language":         identity.language,
        "set_name":         identity.set_name or "",
        "rarity":           identity.rarity or "",
        "overall_score":    condition.overall_score,
        "estimated_value":  None,
        "value_range_low":  None,
        "value_range_high": None,
        "confidence":       condition.confidence,
        "scanned_at":       scanned_at or datetime.utcnow().isoformat(),
        "report":           None,
        "_identity":        identity,
        "_condition":       condition,
    }


def _collection_contains(entry: dict) -> bool:
    return any(
        e["card_name"] == entry["card_name"] and e["card_number"] == entry["card_number"]
        for e in st.session_state["collection"]
    )


# ── Navigation bar ─────────────────────────────────────────────────────────
def _nav() -> None:
    pages = {"accueil": "🏠 Accueil", "scanner": "🔍 Scanner", "collection": "📦 Ma collection"}
    cols = st.columns([1, 1, 1, 4])
    for col, (key, label) in zip(cols, pages.items()):
        with col:
            is_active = st.session_state["page"] == key
            if st.button(label, use_container_width=True, type="primary" if is_active else "secondary"):
                _go(key)
    st.divider()


# ══════════════════════════════════════════════════════════════════════════
# PAGE — ACCUEIL
# ══════════════════════════════════════════════════════════════════════════
def page_accueil() -> None:
    # Header
    h_col, badge_col = st.columns([5, 1])
    with h_col:
        st.title("🎴 CardGrader")
        st.caption("Identifiez, évaluez et estimez la valeur de vos cartes Pokémon TCG")
    with badge_col:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            '<span style="background:#f0a500;color:#000;padding:4px 10px;'
            'border-radius:12px;font-weight:700;font-size:0.8rem;">BETA</span>',
            unsafe_allow_html=True,
        )

    # Scan banner
    st.markdown("---")
    ban_col1, ban_col2 = st.columns(2)
    with ban_col1:
        st.subheader("📸 Scanner une carte")
        st.write("Photographiez ou uploadez recto (+ verso optionnel) pour identifier, grader et estimer la valeur.")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("📷 Prendre une photo", use_container_width=True, type="primary"):
                st.session_state["scanner_mode"] = "camera"
                _go("scanner")
        with b2:
            if st.button("📁 Uploader une photo", use_container_width=True):
                st.session_state["scanner_mode"] = "upload"
                _go("scanner")
    with ban_col2:
        st.markdown(
            """
            <div style='background: linear-gradient(135deg,#1a1a2e,#16213e);
                        border-radius:16px;padding:24px;text-align:center;
                        color:#fff;min-height:120px;display:flex;
                        align-items:center;justify-content:center;font-size:3rem;'>
            🎴✨
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Metrics
    st.markdown("---")
    collection = st.session_state["collection"]
    history    = st.session_state["scan_history"]
    now        = datetime.utcnow()

    total_value  = sum(e["estimated_value"] for e in collection if e.get("estimated_value"))
    scans_month  = sum(
        1 for e in history
        if e.get("scanned_at", "")[:7] == now.strftime("%Y-%m")
    )

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("📦 Ma collection", f"{len(collection)} carte{'s' if len(collection) != 1 else ''}")
    with m2:
        st.metric("💶 Valeur totale", f"{total_value:.2f} €")
    with m3:
        st.metric("📅 Scans ce mois", scans_month)

    # Recent scans
    st.markdown("---")
    st.subheader("🕘 Derniers scans")
    recent = history[-8:][::-1]

    if not recent:
        st.info("Scannez votre première carte pour la voir apparaître ici !")
        if st.button("🔍 Scanner maintenant", type="primary"):
            _go("scanner")
    else:
        n_cols = 4
        for row_start in range(0, len(recent), n_cols):
            row = recent[row_start:row_start + n_cols]
            cols = st.columns(n_cols)
            for col, entry in zip(cols, row):
                with col:
                    flag = LANGUAGE_FLAGS.get(entry["language"], "")
                    score = entry["overall_score"]
                    ts = entry["scanned_at"][:10] if entry.get("scanned_at") else "—"
                    with st.container(border=True):
                        st.markdown(f"**{entry['card_name']}** {flag}")
                        st.caption(f"{entry['card_number']} · {entry.get('set_name') or '—'}")
                        st.write(f"{score_color(score)} {score:.1f}/10")
                        val = entry.get("estimated_value")
                        st.write(f"~{val:.0f} €" if val is not None else "Prix N/A")
                        st.caption(ts)

    # Sell section
    st.markdown("---")
    st.subheader("🛒 Vendre une carte")
    if not collection:
        st.info("Ajoutez des cartes à votre collection pour les vendre.")
    else:
        card_labels = [
            f"{e['card_name']} {e['card_number']} ({e['set_name'] or '—'})"
            for e in collection
        ]
        chosen_idx = st.selectbox("Choisir une carte", range(len(card_labels)), format_func=lambda i: card_labels[i])
        chosen_entry = collection[chosen_idx]
        chosen_report = chosen_entry.get("report")

        sell_col1, sell_col2 = st.columns([2, 1])
        with sell_col1:
            selected_platform = st.selectbox(
                "Plateforme",
                options=list(PLATFORM_LABELS.keys()),
                format_func=lambda k: PLATFORM_LABELS[k],
                key="home_platform",
            )
        with sell_col2:
            selected_lang = st.selectbox("Langue", ["fr", "en"], key="home_lang")

        listing_key = f"home_listing_{chosen_idx}_{selected_platform}_{selected_lang}"
        cached = st.session_state.get(listing_key)

        if st.button("✍️ Générer l'annonce", disabled=cached is not None or chosen_report is None, key="home_gen"):
            from src.agents.listing_generator import ListingGenerator
            with st.spinner("Génération…"):
                try:
                    listing = ListingGenerator(api_key=api_key).generate(chosen_report, selected_platform, selected_lang)
                    st.session_state[listing_key] = listing
                    cached = listing
                except Exception as e:
                    st.error(f"Erreur : {e}")

        if chosen_report is None:
            st.caption("⚠️ Rapport non disponible pour cette entrée de collection.")

        if cached:
            _render_listing(cached, selected_platform)


# ══════════════════════════════════════════════════════════════════════════
# PAGE — SCANNER  (3-step flow: upload → select_card → analyzing → done)
# ══════════════════════════════════════════════════════════════════════════

# ── Scanner helpers ────────────────────────────────────────────────────────

TCGDEX_BASE = "https://api.tcgdex.net/v2"
TCGDEX_LANG_MAP: dict[str, str] = {
    "FR": "fr", "EN": "en", "JP": "ja", "DE": "de",
    "IT": "it", "ES": "es", "KO": "ko", "PT": "pt",
}


def _reset_scanner() -> None:
    """Clear all scanner step-machine state."""
    for key in (
        "step", "id_pending", "tcgdex_candidates", "auto_match_id",
        "auto_match_card", "selected_card", "show_all_cards",
        "current_report", "search_name",
        # legacy keys from old validation form
        "id_confirmed", "id_confirmed_identity",
    ):
        st.session_state.pop(key, None)
    for key in ("_scanner_front_path", "_scanner_back_path"):
        path = st.session_state.pop(key, None)
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


def _tcgdex_search(name: str, lang: str) -> list:
    """Search TCGdex by name; return list of stubs."""
    import httpx
    try:
        resp = httpx.get(
            f"{TCGDEX_BASE}/{lang}/cards",
            params={"name": name},
            timeout=10.0,
        )
        resp.raise_for_status()
        result = resp.json()
        return result if isinstance(result, list) else []
    except Exception as exc:
        print(f"[tcgdex_search] {exc}", file=__import__("sys").stderr)
        return []


def _tcgdex_fetch_card(card_id: str, lang: str) -> dict:
    """Fetch a full TCGdex card by its global id."""
    import httpx
    resp = httpx.get(f"{TCGDEX_BASE}/{lang}/cards/{card_id}", timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _compute_auto_match(identity, candidates: list, lang: str):
    """Return (matched_id, full_card_or_None) for the best localId+cardCount match."""
    from src.tools.card_lookup import _number_matches, _extract_set_total
    import httpx, sys

    local_matches = [
        c for c in candidates
        if _number_matches(identity.number, str(c.get("localId") or c.get("id", "")))
    ]
    if not local_matches:
        return None, None

    total_in_set = _extract_set_total(identity.number)

    if len(local_matches) == 1 or total_in_set is None:
        cid = local_matches[0]["id"]
        print(f"[auto-match] Suggestion: {cid} (single localId match)", file=sys.stderr)
        try:
            full = _tcgdex_fetch_card(cid, lang)
            return cid, full
        except Exception:
            return cid, None

    # Multiple local matches — disambiguate by cardCount
    perfect = acceptable = None
    perfect_card = acceptable_card = None
    for stub in local_matches:
        cid = stub.get("id")
        try:
            full = _tcgdex_fetch_card(cid, lang)
        except Exception:
            continue
        card_count = (full.get("set") or {}).get("cardCount") or {}
        official   = card_count.get("official")
        total      = card_count.get("total")
        print(f"[auto-match] {cid}: cardCount={card_count}", file=sys.stderr)
        if official == total_in_set:
            print(f"[auto-match] Suggestion: {cid} (cardCount.official={official} == total={total_in_set})", file=sys.stderr)
            return cid, full
        if total == total_in_set and acceptable is None:
            acceptable, acceptable_card = cid, full

    if acceptable:
        return acceptable, acceptable_card
    cid = local_matches[0]["id"]
    try:
        full = _tcgdex_fetch_card(cid, lang)
    except Exception:
        full = None
    return cid, full


def _card_image_url(card: dict, quality: str = "high") -> str:
    base = card.get("image", "")
    return f"{base}/{quality}.webp" if base else ""


def _render_card_tile(card: dict, btn_label: str, btn_key: str, btn_type: str = "secondary") -> bool:
    """Render one card tile (image + info + button). Returns True when button clicked."""
    img_url = _card_image_url(card, "high")
    fallback = _card_image_url(card, "low")
    set_name = (card.get("set") or {}).get("name", "")
    local_id = card.get("localId", card.get("id", ""))

    # Display image — try high quality, fallback shown via alt text
    if img_url:
        try:
            st.image(img_url, width=150)
        except Exception:
            if fallback:
                st.image(fallback, width=150)
            else:
                st.markdown("🃏")
    else:
        st.markdown("🃏")

    st.caption(f"**{local_id}** — {set_name}")
    return st.button(btn_label, key=btn_key, use_container_width=True, type=btn_type)


# ── Main scanner page ──────────────────────────────────────────────────────

def page_scanner() -> None:
    step = st.session_state.get("step", "upload")

    hcol, bcol = st.columns([5, 1])
    with hcol:
        st.header("🔍 Scanner une carte")
    with bcol:
        if step != "upload":
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Nouvelle analyse", use_container_width=True):
                _reset_scanner()
                st.rerun()

    # ── STEP: upload ────────────────────────────────────────────────────────
    if step == "upload":
        default_mode = st.session_state.get("scanner_mode", "upload")
        mode_options = ["📁 Uploader des photos", "📷 Prendre en photo"]
        default_index = 1 if default_mode == "camera" else 0
        capture_mode = st.radio(
            "Mode de capture", mode_options, index=default_index,
            horizontal=True, label_visibility="collapsed",
        )

        front_image = back_image = None
        col_front, col_back = st.columns(2)

        if capture_mode == "📁 Uploader des photos":
            with col_front:
                st.markdown("**📸 Recto (obligatoire)**")
                front_file = st.file_uploader(
                    "Recto", type=["jpg", "jpeg", "png", "webp"],
                    key="upload_front", label_visibility="collapsed",
                )
                if front_file:
                    front_image = front_file
                    st.image(front_file, use_container_width=True)
            with col_back:
                st.markdown("**📸 Verso (optionnel)**")
                back_file = st.file_uploader(
                    "Verso", type=["jpg", "jpeg", "png", "webp"],
                    key="upload_back", label_visibility="collapsed",
                )
                if back_file:
                    back_image = back_file
                    st.image(back_file, use_container_width=True)
        else:
            with col_front:
                st.markdown("**📸 Recto (obligatoire)**")
                front_cam = st.camera_input("Recto", key="cam_front", label_visibility="collapsed")
                if front_cam:
                    front_image = front_cam
            with col_back:
                st.markdown("**📸 Verso (optionnel)**")
                back_cam = st.camera_input("Verso", key="cam_back", label_visibility="collapsed")
                if back_cam:
                    back_image = back_cam

        st.write("")
        _, btn_col, _ = st.columns([2, 3, 2])
        with btn_col:
            analyse = st.button(
                "🔍 Analyser ma carte",
                disabled=front_image is None,
                use_container_width=True,
                type="primary",
            )

        if analyse and front_image is not None:
            # Save temp files
            try:
                front_path = save_uploaded(front_image, _ext(front_image))
                back_path  = save_uploaded(back_image, _ext(back_image)) if back_image else None
            except Exception as e:
                st.error(f"Impossible de sauvegarder les images : {e}")
                return
            st.session_state["_scanner_front_path"] = front_path
            st.session_state["_scanner_back_path"]  = back_path

            # Step 1 — vision identification
            from src.agents.identifier import CardIdentifierAgent
            with st.spinner("🔍 Identification de la carte…"):
                try:
                    identity = CardIdentifierAgent(api_key=api_key).identify(front_path)
                    st.session_state["id_pending"] = identity
                except Exception as e:
                    st.error(f"Identification échouée : {e}")
                    return

            identity = st.session_state["id_pending"]
            lang = TCGDEX_LANG_MAP.get(identity.language, "en")

            # Step 2 — TCGdex search
            search_name = identity.name
            with st.spinner(f"📚 Recherche '{search_name}' dans TCGdex…"):
                candidates = _tcgdex_search(search_name, lang)
            st.session_state["tcgdex_candidates"] = candidates
            st.session_state["search_name"]       = search_name

            # Step 3 — auto-match
            if candidates:
                with st.spinner("🎯 Calcul de la suggestion…"):
                    match_id, match_card = _compute_auto_match(identity, candidates, lang)
                st.session_state["auto_match_id"]   = match_id
                st.session_state["auto_match_card"]  = match_card
            else:
                st.session_state["auto_match_id"]   = None
                st.session_state["auto_match_card"]  = None

            st.session_state["step"] = "select_card"
            st.rerun()

    # ── STEP: select_card ───────────────────────────────────────────────────
    elif step == "select_card":
        identity      = st.session_state.get("id_pending")
        candidates    = st.session_state.get("tcgdex_candidates", [])
        auto_match_id = st.session_state.get("auto_match_id")
        auto_match_card = st.session_state.get("auto_match_card")
        lang          = TCGDEX_LANG_MAP.get(identity.language if identity else "EN", "en")
        search_name   = st.session_state.get("search_name", identity.name if identity else "")

        if identity:
            st.success(f"✅ Carte détectée : **{identity.name}** ({identity.language}) — numéro lu : `{identity.number}`")

        if not candidates:
            # No results — offer retry
            st.warning(f"Aucune carte trouvée pour « {search_name} » dans TCGdex.")
            new_name = st.text_input("Essayez un autre nom :", value=search_name, key="retry_name")
            if st.button("🔍 Rechercher", type="primary"):
                with st.spinner(f"Recherche '{new_name}'…"):
                    new_candidates = _tcgdex_search(new_name, lang)
                st.session_state["tcgdex_candidates"] = new_candidates
                st.session_state["search_name"]       = new_name
                if new_candidates and identity:
                    with st.spinner("Calcul suggestion…"):
                        mid, mcard = _compute_auto_match(identity, new_candidates, lang)
                    st.session_state["auto_match_id"]  = mid
                    st.session_state["auto_match_card"] = mcard
                else:
                    st.session_state["auto_match_id"]  = None
                    st.session_state["auto_match_card"] = None
                st.rerun()
            return

        show_all   = st.session_state.get("show_all_cards", False)
        MAX_SHOWN  = 12
        others     = [c for c in candidates if c.get("id") != auto_match_id]
        display_others = others if show_all else others[:MAX_SHOWN]

        # ── AI suggestion ──────────────────────────────────────────────────
        if auto_match_id and auto_match_card:
            with st.container(border=True):
                st.markdown("#### ✅ Suggestion de l'IA")
                tile_col, info_col = st.columns([1, 2])
                with tile_col:
                    img_url = _card_image_url(auto_match_card, "high")
                    if img_url:
                        st.image(img_url, width=180)
                with info_col:
                    set_info = auto_match_card.get("set") or {}
                    st.markdown(f"**{auto_match_card.get('name', '')}**")
                    st.write(f"Set : {set_info.get('name', '—')}")
                    st.write(f"N° : {auto_match_card.get('localId', auto_match_id)}")
                    cc = set_info.get("cardCount") or {}
                    if cc.get("official"):
                        st.caption(f"Set de {cc['official']} cartes officielles")
                    if st.button("✅ Confirmer cette carte", type="primary", key="confirm_auto"):
                        st.session_state["selected_card"] = auto_match_card
                        st.session_state["step"]          = "analyzing"
                        st.rerun()
        elif auto_match_id:
            # We have an ID but no full card fetched — show a simpler confirm
            st.info(f"Suggestion IA : `{auto_match_id}`")
            if st.button("✅ Confirmer cette suggestion", type="primary", key="confirm_auto_id"):
                with st.spinner("Chargement de la carte…"):
                    try:
                        full = _tcgdex_fetch_card(auto_match_id, lang)
                        st.session_state["selected_card"] = full
                    except Exception as e:
                        st.error(f"Erreur : {e}")
                        return
                st.session_state["step"] = "analyzing"
                st.rerun()

        # ── Other versions ─────────────────────────────────────────────────
        if display_others:
            st.markdown("---")
            label = "Autres versions :" if auto_match_id else "Sélectionnez votre carte :"
            st.subheader(label)

            n_cols = 4
            for row_start in range(0, len(display_others), n_cols):
                row = display_others[row_start:row_start + n_cols]
                cols = st.columns(n_cols)
                for col, card in zip(cols, row):
                    with col:
                        cid = card.get("id", "")
                        clicked = _render_card_tile(
                            card,
                            btn_label="C'est celle-ci",
                            btn_key=f"pick_{cid}",
                        )
                        if clicked:
                            with st.spinner("Chargement de la carte…"):
                                try:
                                    full = _tcgdex_fetch_card(cid, lang)
                                    st.session_state["selected_card"] = full
                                except Exception as e:
                                    st.error(f"Impossible de charger la carte : {e}")
                                    return
                            st.session_state["step"] = "analyzing"
                            st.rerun()

            if not show_all and len(others) > MAX_SHOWN:
                remaining = len(others) - MAX_SHOWN
                st.caption(f"… et {remaining} autre{'s' if remaining > 1 else ''} version(s)")
                if st.button("Voir plus", key="show_all_btn"):
                    st.session_state["show_all_cards"] = True
                    st.rerun()

    # ── STEP: analyzing ─────────────────────────────────────────────────────
    elif step == "analyzing":
        selected_card = st.session_state.get("selected_card")
        front_path    = st.session_state.get("_scanner_front_path")
        back_path     = st.session_state.get("_scanner_back_path")
        identity      = st.session_state.get("id_pending")

        if not selected_card or not front_path or not identity:
            st.error("Données manquantes — veuillez rescanner.")
            _reset_scanner()
            st.rerun()
            return

        from src.evaluation.grader import CardGrader
        from src.evaluation.scoring import ScoringEngine
        from src.tools.pricing import PricingTool

        # Enrich identity from selected TCGdex card
        set_info = selected_card.get("set") or {}
        identity.set_name = identity.set_name or set_info.get("name", "")
        identity.set_code = identity.set_code or set_info.get("id", "").split("-")[0] or None
        identity.rarity   = identity.rarity   or selected_card.get("rarity")

        condition = None
        pricing   = None
        report    = None

        with st.status("Analyse en cours…", expanded=True) as status:

            st.write("🔬 Évaluation de l'état…")
            try:
                condition = CardGrader(api_key=api_key).grade(
                    front_image_path=front_path,
                    back_image_path=back_path,
                )
                st.write(f"✅ Score global : **{condition.overall_score}/10** {score_color(condition.overall_score)}")
            except Exception as e:
                st.error(f"Grading échoué : {e}")

            if condition:
                st.write("💰 Recherche des prix…")
                try:
                    rapidapi_key = os.environ.get("RAPIDAPI_KEY")
                    pricing = PricingTool(rapidapi_key=rapidapi_key).fetch_prices(
                        identity=identity,
                        tcgdex_card=selected_card,
                    )
                    lang_tag = " (prix langue)" if pricing.language_specific else ""
                    st.write(
                        f"✅ Prix NM : **{pricing.raw_price:.2f} {pricing.currency}**"
                        f"{lang_tag} — source : {pricing.source_detail}"
                    )
                except Exception as e:
                    st.warning(f"⚠️ Récupération des prix échouée : {e}")

            if condition and pricing:
                st.write("📊 Calcul du score final…")
                try:
                    report = ScoringEngine().compute_report(
                        identity=identity,
                        condition=condition,
                        pricing=pricing,
                        front_image_path=front_path,
                        back_image_path=back_path,
                    )
                    st.write(f"✅ Valeur estimée : **{report.estimated_value:.2f} {pricing.currency}**")
                except Exception as e:
                    st.error(f"Calcul du score échoué : {e}")

            status.update(label="Analyse terminée ✅", state="complete", expanded=False)

        # Save entry
        if identity and condition:
            try:
                entry = _report_to_entry(report) if report else _partial_entry(identity, condition)
            except Exception:
                entry = _partial_entry(identity, condition)
            st.session_state["current_report"] = entry
            st.session_state["scan_history"].append(entry)
            st.success("✅ Scan sauvegardé dans l'historique")

        # Cleanup temp files
        for path in (front_path, back_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
        st.session_state.pop("_scanner_front_path", None)
        st.session_state.pop("_scanner_back_path", None)

        st.session_state["step"] = "done"
        st.rerun()

    # ── STEP: done ──────────────────────────────────────────────────────────
    elif step == "done":
        entry = st.session_state.get("current_report")
        if entry:
            _render_report(entry, front_image=None)


def _render_report(entry: dict, front_image=None) -> None:
    """Render identity / condition / pricing sections from a session_state entry."""
    report    = entry.get("report")
    identity  = report.identity  if report else entry.get("_identity")
    condition = report.condition if report else entry.get("_condition")
    pricing   = report.pricing   if report else None

    if not identity or not condition:
        return

    st.divider()

    # Section 1 — Identity
    st.subheader("📋 Identité de la carte")
    id_img_col, id_info_col = st.columns([1, 2])
    with id_img_col:
        if front_image:
            st.image(front_image, width=200)
    with id_info_col:
        flag = LANGUAGE_FLAGS.get(identity.language, "")
        st.header(identity.name)
        st.write(f"**Numéro :** {identity.number}")
        st.write(f"**Set :** {identity.set_name or '—'}")
        st.write(f"**Langue :** {flag} {identity.language}")
        st.write(f"**Rareté :** {identity.rarity or '—'}")
        conf_pct = int(condition.confidence * 100)
        st.caption(f"Confiance identification : {conf_pct}%")

    # Section 2 — Condition
    st.divider()
    st.subheader("🔬 État de la carte")
    score = condition.overall_score
    st.metric(label=f"Score global {score_color(score)}", value=f"{score:.1f} / 10")

    prog_col1, prog_col2 = st.columns(2)
    sub_scores = [
        ("🎯 Centrage", condition.centering,  "centering 15%"),
        ("🔲 Coins",    condition.corners,    "corners 30%"),
        ("📏 Bords",    condition.edges,      "edges 25%"),
        ("✨ Surface",  condition.surface,    "surface 30%"),
    ]
    for i, (label, score_val, weight) in enumerate(sub_scores):
        col = prog_col1 if i % 2 == 0 else prog_col2
        with col:
            st.write(f"**{label}** — {score_val:.1f}/10")
            st.progress(score_val / 10)
            st.caption(weight)

    with st.expander("Voir les détails de l'évaluation"):
        for label, score_val, _ in sub_scores:
            st.write(f"- **{label.split(' ', 1)[1]} :** {score_val:.1f}/10")
        st.write(f"- **Score composite :** {condition.overall_score:.1f}/10")
        if hasattr(condition, "details") and condition.details:
            st.write(condition.details)
        st.caption("Pondérations PSA : corners 30%, surface 30%, edges 25%, centering 15%")

    # Section 3 — Pricing
    st.divider()
    st.subheader("💰 Estimation de valeur")

    if pricing is None:
        st.warning("⚠️ Prix indisponibles — carte introuvable dans TCGdex ou résolution échouée.")
    else:
        curr = pricing.currency
        p1, p2, p3 = st.columns(3)
        with p1:
            st.metric("Prix référence (NM)", f"{pricing.raw_price:.2f} {curr}")
        with p2:
            st.metric(
                "Estimation selon état",
                f"{report.estimated_value:.2f} {curr}",
                delta=f"{report.value_range_low:.2f} — {report.value_range_high:.2f} {curr}",
                delta_color="off",
            )
        with p3:
            st.metric("Confiance", f"{int(report.confidence_score * 100)} %")
        st.caption(f"Source : {pricing.source_detail}")
        if not pricing.language_specific:
            lang_name = LANGUAGE_FLAGS.get(identity.language, "") + " " + identity.language
            st.warning(
                f"⚠️ Prix basé sur le marché global CardMarket. "
                f"Le prix spécifique pour les cartes {lang_name.strip()} peut varier significativement."
            )
        grade_rows = {
            "PSA 10": pricing.grade_10, "PSA 9": pricing.grade_9,
            "PSA 7": pricing.grade_7, "PSA 5": pricing.grade_5, "PSA 3": pricing.grade_3,
        }
        available_grades = {k: v for k, v in grade_rows.items() if v is not None}
        if available_grades:
            st.write("**Prix par grade PSA :**")
            import pandas as pd
            df = pd.DataFrame(
                [{"Grade": k, f"Prix ({curr})": f"{v:.2f}"} for k, v in available_grades.items()]
            )
            st.dataframe(df, hide_index=True, use_container_width=False)

    # Add to collection
    st.divider()
    already_in = _collection_contains(entry)
    if already_in:
        st.success("✅ Carte déjà dans votre collection.")
    else:
        if st.button("➕ Ajouter à ma collection", type="primary"):
            st.session_state["collection"].append(entry)
            st.success("Carte ajoutée à votre collection !")
            st.rerun()

    # Section 4 — Sell (only available with full report for ListingGenerator)
    if report is not None:
        st.divider()
        st.header("🛒 Vendre cette carte")
        sell_col1, sell_col2 = st.columns([2, 1])
        with sell_col1:
            selected_platform = st.selectbox(
                "Plateforme de vente",
                options=list(PLATFORM_LABELS.keys()),
                format_func=lambda k: PLATFORM_LABELS[k],
            )
        with sell_col2:
            selected_lang = st.selectbox("Langue de l'annonce", ["fr", "en"])

        listing_cache_key = f"listing_{selected_platform}_{selected_lang}"
        cached_listing = st.session_state.get(listing_cache_key)

        if st.button("✍️ Générer l'annonce", type="primary", disabled=cached_listing is not None):
            from src.agents.listing_generator import ListingGenerator
            with st.spinner("Génération de l'annonce en cours…"):
                try:
                    listing = ListingGenerator(api_key=api_key).generate(report, selected_platform, selected_lang)
                    st.session_state[listing_cache_key] = listing
                    cached_listing = listing
                except Exception as e:
                    st.error(f"Erreur lors de la génération : {e}")

        if cached_listing:
            _render_listing(cached_listing, selected_platform)


def _render_listing(listing: dict, platform: str) -> None:
    """Render a generated listing dict."""
    st.subheader(listing["title"])
    st.text_area(
        "Description (modifiable)",
        value=listing["description"],
        height=200,
        key=f"desc_{platform}_{listing.get('suggested_price', '')}",
    )
    price_col, tag_col = st.columns([1, 2])
    with price_col:
        st.metric("Prix suggéré", f"{listing['suggested_price']:.2f} €")
    with tag_col:
        st.write("**Tags :**")
        st.write("  ".join(f"`{t}`" for t in listing.get("tags", [])))
    copy_col, link_col = st.columns(2)
    with copy_col:
        st.code(f"{listing['title']}\n\n{listing['description']}", language=None)
        st.caption("Sélectionnez le texte ci-dessus pour le copier.")
    with link_col:
        st.link_button(
            f"📤 Créer l'annonce sur {PLATFORM_LABELS.get(platform, platform)}",
            url=listing["redirect_url"],
            use_container_width=True,
        )
    regen_key = f"regen_{platform}_{listing.get('suggested_price', '')}"
    if st.button("🔄 Régénérer", key=regen_key):
        cache_key = f"listing_{platform}_{listing.get('suggested_price', '')}"
        # Clear any matching listing keys for this platform
        for k in list(st.session_state.keys()):
            if k.startswith(f"listing_{platform}_"):
                del st.session_state[k]
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# PAGE — MA COLLECTION
# ══════════════════════════════════════════════════════════════════════════
def page_collection() -> None:
    collection = st.session_state["collection"]
    total_value = sum(e["estimated_value"] for e in collection if e.get("estimated_value"))

    # Header
    h_col, v_col = st.columns([3, 1])
    with h_col:
        st.header(f"📦 Ma collection — {len(collection)} carte{'s' if len(collection) != 1 else ''}")
    with v_col:
        st.metric("Valeur totale", f"{total_value:.2f} €")

    if not collection:
        st.info("Votre collection est vide. Scannez une carte pour commencer !")
        if st.button("🔍 Scanner une carte", type="primary"):
            _go("scanner")
        return

    # Sort options
    sort_by = st.radio(
        "Trier par",
        ["Date d'ajout", "Valeur estimée", "Score d'état"],
        horizontal=True,
    )

    sort_key_map = {
        "Date d'ajout":    lambda e: e.get("scanned_at") or "",
        "Valeur estimée":  lambda e: e.get("estimated_value") or 0,
        "Score d'état":    lambda e: e.get("overall_score") or 0,
    }
    sorted_collection = sorted(collection, key=sort_key_map[sort_by], reverse=True)

    # Grid
    n_cols = 4
    to_remove = None

    for row_start in range(0, len(sorted_collection), n_cols):
        row = sorted_collection[row_start:row_start + n_cols]
        cols = st.columns(n_cols)
        for col, entry in zip(cols, row):
            with col:
                flag  = LANGUAGE_FLAGS.get(entry["language"], "")
                score = entry["overall_score"]
                with st.container(border=True):
                    st.markdown(f"**{entry['card_name']}** {flag}")
                    st.caption(f"{entry['card_number']} · {entry.get('set_name') or '—'}")
                    st.write(f"{score_color(score)} {score:.1f}/10")
                    val = entry.get("estimated_value")
                    st.metric("Valeur", f"{val:.0f} €" if val is not None else "N/A", label_visibility="collapsed")

                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("🛒 Vendre", key=f"sell_{entry['card_name']}_{entry['card_number']}_{row_start}", use_container_width=True):
                            st.session_state["sell_target"] = entry
                            st.rerun()
                    with btn_col2:
                        if st.button("🗑️ Retirer", key=f"rm_{entry['card_name']}_{entry['card_number']}_{row_start}", use_container_width=True):
                            to_remove = entry

    if to_remove is not None:
        st.session_state["collection"] = [
            e for e in collection
            if not (e["card_name"] == to_remove["card_name"] and e["card_number"] == to_remove["card_number"])
        ]
        st.rerun()

    # Sell panel
    sell_target = st.session_state.get("sell_target")
    if sell_target and sell_target in st.session_state["collection"]:
        st.divider()
        st.subheader(f"🛒 Vendre : {sell_target['card_name']} {sell_target['card_number']}")
        sell_report = sell_target.get("report")

        s1, s2 = st.columns([2, 1])
        with s1:
            sell_platform = st.selectbox(
                "Plateforme",
                options=list(PLATFORM_LABELS.keys()),
                format_func=lambda k: PLATFORM_LABELS[k],
                key="coll_platform",
            )
        with s2:
            sell_lang = st.selectbox("Langue", ["fr", "en"], key="coll_lang")

        coll_listing_key = f"coll_listing_{sell_target['card_name']}_{sell_target['card_number']}_{sell_platform}_{sell_lang}"
        cached = st.session_state.get(coll_listing_key)

        if st.button("✍️ Générer l'annonce", disabled=cached is not None or sell_report is None, key="coll_gen"):
            from src.agents.listing_generator import ListingGenerator
            with st.spinner("Génération…"):
                try:
                    listing = ListingGenerator(api_key=api_key).generate(sell_report, sell_platform, sell_lang)
                    st.session_state[coll_listing_key] = listing
                    cached = listing
                except Exception as e:
                    st.error(f"Erreur : {e}")

        if sell_report is None:
            st.caption("⚠️ Rapport non disponible pour cette entrée.")
        if cached:
            _render_listing(cached, sell_platform)

    # Total value banner
    st.divider()
    st.markdown(
        f"<div style='text-align:center;font-size:1.8rem;font-weight:700;padding:16px;'>"
        f"💶 Valeur totale de la collection : {total_value:.2f} €"
        f"</div>",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════
_nav()

page = st.session_state["page"]
if page == "accueil":
    page_accueil()
elif page == "scanner":
    page_scanner()
elif page == "collection":
    page_collection()
