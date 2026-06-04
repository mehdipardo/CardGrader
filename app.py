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
        "page":           "accueil",
        "scan_history":   [],
        "collection":     [],
        "current_report": None,
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
    """Serialize a CardReport into a flat session_state entry."""
    return {
        "card_name":       report.identity.name,
        "card_number":     report.identity.number,
        "language":        report.identity.language,
        "set_name":        report.identity.set_name or "",
        "rarity":          report.identity.rarity or "",
        "overall_score":   report.condition.overall_score,
        "estimated_value": report.estimated_value,
        "value_range_low": report.value_range_low,
        "value_range_high":report.value_range_high,
        "confidence":      report.confidence_score,
        "scanned_at":      scanned_at or datetime.utcnow().isoformat(),
        "report":          report,
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
                        st.caption(f"{entry['card_number']} · {entry['set_name'] or '—'}")
                        st.write(f"{score_color(score)} {score:.1f}/10")
                        st.write(f"~{entry['estimated_value']:.0f} €")
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
# PAGE — SCANNER
# ══════════════════════════════════════════════════════════════════════════
def page_scanner() -> None:
    st.header("🔍 Scanner une carte")

    # Capture mode — honour pre-selection from homepage buttons
    default_mode = st.session_state.get("scanner_mode", "upload")
    mode_options = ["📁 Uploader des photos", "📷 Prendre en photo"]
    default_index = 1 if default_mode == "camera" else 0

    capture_mode = st.radio(
        "Mode de capture",
        mode_options,
        index=default_index,
        horizontal=True,
        label_visibility="collapsed",
    )

    front_image = None
    back_image  = None

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

    # Analyse button
    st.write("")
    _, btn_col, _ = st.columns([2, 3, 2])
    with btn_col:
        analyse = st.button(
            "🔍 Analyser ma carte",
            disabled=front_image is None,
            use_container_width=True,
            type="primary",
        )

    # ── Pipeline ───────────────────────────────────────────────────────────
    if analyse and front_image is not None:
        front_path: Optional[str] = None
        back_path:  Optional[str] = None

        try:
            front_path = save_uploaded(front_image, _ext(front_image))
            if back_image:
                back_path = save_uploaded(back_image, _ext(back_image))
        except Exception as e:
            st.error(f"Impossible de sauvegarder les images : {e}")
            st.stop()

        from src.agents.identifier import CardIdentifierAgent
        from src.evaluation.grader import CardGrader
        from src.evaluation.scoring import ScoringEngine
        from src.models.card import CardIdentity, CardPricing
        from src.tools.card_lookup import CardLookupTool, CardNotFoundError
        from src.tools.pricing import PricingTool

        identity    = None
        tcgdex_card = None
        condition   = None
        pricing     = None
        report      = None
        pricing_unavailable = False

        with st.status("Analyse en cours…", expanded=True) as status:

            st.write("🔍 Identification de la carte…")
            try:
                identity = CardIdentifierAgent(api_key=api_key).identify(front_image_path=front_path)
                st.write(f"✅ Carte détectée : **{identity.name}** {identity.number}")
            except Exception as e:
                st.error(f"Identification échouée : {e}")

            if identity:
                st.write("📚 Résolution dans la base TCGdex…")
                try:
                    tcgdex_card = CardLookupTool().resolve(identity)
                    set_name = (tcgdex_card.get("set") or {}).get("name", "")
                    identity.set_name = identity.set_name or set_name
                    identity.set_code = identity.set_code or tcgdex_card.get("id", "").split("-")[0] or None
                    identity.rarity   = identity.rarity   or tcgdex_card.get("rarity")
                    st.write(f"✅ Set trouvé : **{identity.set_name or tcgdex_card.get('id', '?')}**")
                except CardNotFoundError as e:
                    st.warning(f"⚠️ Carte introuvable dans TCGdex : {e}")
                    pricing_unavailable = True
                except Exception as e:
                    st.warning(f"⚠️ Résolution TCGdex échouée : {e}")
                    pricing_unavailable = True

            if identity:
                st.write("🔬 Évaluation de l'état…")
                try:
                    condition = CardGrader(api_key=api_key).grade(
                        front_image_path=front_path,
                        back_image_path=back_path,
                    )
                    st.write(f"✅ Score global : **{condition.overall_score}/10** {score_color(condition.overall_score)}")
                except Exception as e:
                    st.error(f"Grading échoué : {e}")

            if identity and tcgdex_card and not pricing_unavailable:
                st.write("💰 Recherche des prix…")
                try:
                    rapidapi_key = os.environ.get("RAPIDAPI_KEY")
                    pricing = PricingTool(rapidapi_key=rapidapi_key).fetch_prices(
                        identity=identity,
                        tcgdex_card=tcgdex_card,
                    )
                    lang_tag = " (prix langue)" if pricing.language_specific else ""
                    st.write(f"✅ Prix NM : **{pricing.raw_price:.2f} {pricing.currency}**{lang_tag} — source : {pricing.source_detail}")
                except Exception as e:
                    st.warning(f"⚠️ Récupération des prix échouée : {e}")
                    pricing_unavailable = True

            if identity and condition and pricing:
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

        # Store report and add to scan history
        if report:
            entry = _report_to_entry(report)
            st.session_state["current_report"] = entry
            st.session_state["scan_history"].append(entry)

        # Cleanup temp files
        for path in (front_path, back_path):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    # ── Display report ─────────────────────────────────────────────────────
    entry  = st.session_state.get("current_report")
    report = entry["report"] if entry and entry.get("report") else None

    if report:
        _render_report(report, entry, front_image)


def _render_report(report, entry: dict, front_image) -> None:
    """Render identity / condition / pricing sections for a CardReport."""
    identity  = report.identity
    condition = report.condition
    pricing   = report.pricing

    st.divider()

    # Section 1 — Identity
    st.subheader("📋 Identité de la carte")
    id_img_col, id_info_col = st.columns([1, 2])
    with id_img_col:
        if front_image:
            st.image(front_image, width=200)
    with id_info_col:
        flag = LANGUAGE_FLAGS.get(identity.language, "")
        st.header(f"{identity.name}")
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
        st.caption("Pondérations PSA : corners 30%, surface 30%, edges 25%, centering 15%")

    # Section 3 — Pricing
    st.divider()
    st.subheader("💰 Estimation de valeur")
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

    # Add to collection button
    st.divider()
    already_in = _collection_contains(entry)
    if already_in:
        st.success("✅ Carte déjà dans votre collection.")
    else:
        if st.button("➕ Ajouter à ma collection", type="primary"):
            st.session_state["collection"].append(entry)
            st.success("Carte ajoutée à votre collection !")
            st.rerun()

    # Section 4 — Sell
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
        "Date d'ajout":    lambda e: e.get("scanned_at", ""),
        "Valeur estimée":  lambda e: e.get("estimated_value", 0),
        "Score d'état":    lambda e: e.get("overall_score", 0),
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
                    st.metric("Valeur", f"{entry['estimated_value']:.0f} €", label_visibility="collapsed")

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
