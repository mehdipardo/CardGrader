"""CardGrader — Streamlit UI for Pokémon TCG card analysis."""

import os
import tempfile
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

# ── Page config (must be first Streamlit call) ─────────────────────────────
st.set_page_config(
    page_title="CardGrader",
    page_icon="🎴",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv()

# ── Constants ──────────────────────────────────────────────────────────────
LANGUAGE_FLAGS: dict[str, str] = {
    "FR": "🇫🇷", "EN": "🇬🇧", "JP": "🇯🇵",
    "DE": "🇩🇪", "IT": "🇮🇹", "ES": "🇪🇸",
    "KO": "🇰🇷", "PT": "🇧🇷",
}

GITHUB_URL = "https://github.com/mehdipardo/CardGrader"


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎴 CardGrader")
    st.caption("v0.1")
    st.divider()

    st.subheader("À propos")
    st.write(
        "Agent IA d'évaluation de cartes Pokémon TCG. "
        "Identification par vision, évaluation de l'état, estimation de prix."
    )

    st.subheader("Stack technique")
    st.markdown(
        "🤖 **Claude Vision** — identification + grading\n\n"
        "📚 **TCGdex** — base de données multilingue\n\n"
        "💰 **CardMarket** — prix EU"
    )

    st.link_button("📂 Code source GitHub", GITHUB_URL)
    st.divider()
    st.write("**Langues supportées :**")
    st.write(" ".join(LANGUAGE_FLAGS.values()))


# ── API key guard ──────────────────────────────────────────────────────────
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    st.error(
        "❌ **ANTHROPIC_API_KEY manquante.** "
        "Ajoutez-la dans votre fichier `.env` ou variables d'environnement."
    )
    st.stop()


# ── Header ─────────────────────────────────────────────────────────────────
st.title("🎴 CardGrader — Pokémon TCG Card Analyzer")
st.subheader("Identifiez, évaluez et estimez la valeur de vos cartes")
st.divider()


# ── Mode de capture ────────────────────────────────────────────────────────
capture_mode = st.radio(
    "Mode de capture",
    ["📁 Uploader des photos", "📷 Prendre en photo"],
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

else:  # camera
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


# ── Analyse button ─────────────────────────────────────────────────────────
st.write("")
_, btn_col, _ = st.columns([2, 3, 2])
with btn_col:
    analyse = st.button(
        "🔍 Analyser ma carte",
        disabled=front_image is None,
        use_container_width=True,
        type="primary",
    )


# ── Pipeline ───────────────────────────────────────────────────────────────
def save_uploaded(file_like, suffix: str) -> str:
    """Write an uploaded/camera file to a named temp file; return its path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file_like.read() if hasattr(file_like, "read") else file_like.getvalue())
    tmp.flush()
    return tmp.name


def score_color(score: float) -> str:
    if score >= 8:
        return "🟢"
    if score >= 5:
        return "🟠"
    return "🔴"


if analyse and front_image is not None:
    # Determine file extensions
    def _ext(f) -> str:
        name = getattr(f, "name", "image.jpg")
        return Path(name).suffix or ".jpg"

    front_path: Optional[str] = None
    back_path:  Optional[str] = None

    try:
        front_path = save_uploaded(front_image, _ext(front_image))
        if back_image:
            back_path = save_uploaded(back_image, _ext(back_image))
    except Exception as e:
        st.error(f"Impossible de sauvegarder les images : {e}")
        st.stop()

    # Lazy imports inside the pipeline to avoid slowing cold start
    from src.agents.identifier import CardIdentifierAgent
    from src.evaluation.grader import CardGrader
    from src.evaluation.scoring import ScoringEngine
    from src.models.card import CardIdentity, CardPricing
    from src.tools.card_lookup import CardLookupTool, CardNotFoundError
    from src.tools.pricing import PricingTool

    identity:    Optional[CardIdentity]  = None
    tcgdex_card: Optional[dict]          = None
    condition                            = None
    pricing:     Optional[CardPricing]   = None
    report                               = None
    pricing_unavailable = False

    with st.status("Analyse en cours…", expanded=True) as status:

        # Step 1 — Identify
        st.write("🔍 Identification de la carte…")
        try:
            agent    = CardIdentifierAgent(api_key=api_key)
            identity = agent.identify(front_image_path=front_path)
            st.write(f"✅ Carte détectée : **{identity.name}** {identity.number}")
        except Exception as e:
            st.error(f"Identification échouée : {e}")

        # Step 2 — Resolve (TCGDex)
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

        # Step 3 — Grade
        if identity:
            st.write("🔬 Évaluation de l'état…")
            try:
                grader    = CardGrader(api_key=api_key)
                condition = grader.grade(
                    front_image_path=front_path,
                    back_image_path=back_path,
                )
                st.write(
                    f"✅ Score global : **{condition.overall_score}/10** "
                    f"{score_color(condition.overall_score)}"
                )
            except Exception as e:
                st.error(f"Grading échoué : {e}")

        # Step 4 — Price
        if identity and tcgdex_card and not pricing_unavailable:
            st.write("💰 Recherche des prix…")
            try:
                rapidapi_key = os.environ.get("RAPIDAPI_KEY")
                pricing = PricingTool(rapidapi_key=rapidapi_key).fetch_prices(
                    identity=identity,
                    tcgdex_card=tcgdex_card,
                )
                src = pricing.source_detail
                lang_tag = " (prix langue)" if pricing.language_specific else ""
                st.write(
                    f"✅ Prix NM : **{pricing.raw_price:.2f} {pricing.currency}**"
                    f"{lang_tag} — source : {src}"
                )
            except Exception as e:
                st.warning(f"⚠️ Récupération des prix échouée : {e}")
                pricing_unavailable = True

        # Step 5 — Score
        if identity and condition and pricing:
            st.write("📊 Calcul du score final…")
            try:
                engine = ScoringEngine()
                report = engine.compute_report(
                    identity=identity,
                    condition=condition,
                    pricing=pricing,
                    front_image_path=front_path,
                    back_image_path=back_path,
                )
                st.write(
                    f"✅ Valeur estimée : **{report.estimated_value:.2f} {pricing.currency}**"
                )
            except Exception as e:
                st.error(f"Calcul du score échoué : {e}")

        status.update(label="Analyse terminée ✅", state="complete", expanded=False)

    # ── Report ─────────────────────────────────────────────────────────────
    st.divider()

    # Section 1 — Identity
    if identity:
        st.subheader("📋 Identité de la carte")
        id_img_col, id_info_col = st.columns([1, 2])

        with id_img_col:
            st.image(front_image, width=200)

        with id_info_col:
            flag = LANGUAGE_FLAGS.get(identity.language, "")
            st.header(f"{identity.name}")
            st.write(f"**Numéro :** {identity.number}")
            st.write(f"**Set :** {identity.set_name or '—'}")
            st.write(f"**Langue :** {flag} {identity.language}")
            st.write(f"**Rareté :** {identity.rarity or '—'}")
            if condition:
                conf_pct = int(condition.confidence * 100)
                st.caption(f"Confiance identification : {conf_pct}%")

    # Section 2 — Condition
    if condition:
        st.divider()
        st.subheader("🔬 État de la carte")

        score = condition.overall_score
        color = score_color(score)
        st.metric(label=f"Score global {color}", value=f"{score:.1f} / 10")

        prog_col1, prog_col2 = st.columns(2)
        sub_scores = [
            ("🎯 Centrage",  condition.centering, "centering 15%"),
            ("🔲 Coins",     condition.corners,   "corners 30%"),
            ("📏 Bords",     condition.edges,     "edges 25%"),
            ("✨ Surface",   condition.surface,   "surface 30%"),
        ]
        for i, (label, score_val, weight) in enumerate(sub_scores):
            col = prog_col1 if i % 2 == 0 else prog_col2
            with col:
                st.write(f"**{label}** — {score_val:.1f}/10")
                st.progress(score_val / 10)
                st.caption(weight)

        # Detailed observations from the grader response (stored in tcgdex_card
        # for now — actual detail fields come from the raw response if we expose them)
        with st.expander("Voir les détails de l'évaluation"):
            st.write(f"- **Centrage :** {condition.centering:.1f}/10")
            st.write(f"- **Coins :** {condition.corners:.1f}/10")
            st.write(f"- **Bords :** {condition.edges:.1f}/10")
            st.write(f"- **Surface :** {condition.surface:.1f}/10")
            st.write(f"- **Score composite :** {condition.overall_score:.1f}/10")
            st.caption(
                "Pondérations PSA : corners 30%, surface 30%, edges 25%, centering 15%"
            )

    # Section 3 — Pricing
    st.divider()
    st.subheader("💰 Estimation de valeur")

    if pricing_unavailable or pricing is None:
        st.warning("⚠️ Prix indisponibles — carte introuvable dans TCGdex.")
    else:
        curr = pricing.currency
        price_col, range_col, conf_col = st.columns(3)

        with price_col:
            st.metric(
                label="Prix référence (NM)",
                value=f"{pricing.raw_price:.2f} {curr}",
            )

        if report:
            with range_col:
                st.metric(
                    label="Estimation selon état",
                    value=f"{report.estimated_value:.2f} {curr}",
                    delta=f"{report.value_range_low:.2f} — {report.value_range_high:.2f} {curr}",
                    delta_color="off",
                )
            with conf_col:
                st.metric(
                    label="Confiance",
                    value=f"{int(report.confidence_score * 100)} %",
                )
        else:
            with range_col:
                st.metric(label="Estimation selon état", value="—")
            with conf_col:
                st.metric(label="Confiance", value="—")

        st.caption(f"Source : {pricing.source_detail}")

        if not pricing.language_specific:
            lang_name = LANGUAGE_FLAGS.get(identity.language, "") + " " + (identity.language if identity else "")
            st.warning(
                f"⚠️ Prix basé sur le marché global CardMarket. "
                f"Le prix spécifique pour les cartes {lang_name.strip()} "
                f"peut varier significativement."
            )

        # PSA grade table if any grades are available
        grade_rows = {
            "PSA 10": pricing.grade_10,
            "PSA 9":  pricing.grade_9,
            "PSA 7":  pricing.grade_7,
            "PSA 5":  pricing.grade_5,
            "PSA 3":  pricing.grade_3,
        }
        available_grades = {k: v for k, v in grade_rows.items() if v is not None}
        if available_grades:
            st.write("**Prix par grade PSA :**")
            import pandas as pd
            df = pd.DataFrame(
                [{"Grade": k, f"Prix ({curr})": f"{v:.2f}"} for k, v in available_grades.items()]
            )
            st.dataframe(df, hide_index=True, use_container_width=False)

    # ── Section 4 — Sell ───────────────────────────────────────────────────
    if report:
        st.divider()
        st.header("🛒 Vendre cette carte")

        PLATFORM_LABELS: dict[str, str] = {
            "vinted":     "Vinted",
            "ebay":       "eBay",
            "leboncoin":  "LeBonCoin",
            "facebook":   "Facebook Marketplace",
            "cardmarket": "CardMarket",
        }

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

        generate_btn = st.button(
            "✍️ Générer l'annonce",
            type="primary",
            disabled=cached_listing is not None,
        )

        if generate_btn:
            from src.agents.listing_generator import ListingGenerator
            with st.spinner("Génération de l'annonce en cours…"):
                try:
                    generator = ListingGenerator(api_key=api_key)
                    listing = generator.generate(report, selected_platform, selected_lang)
                    st.session_state[listing_cache_key] = listing
                    cached_listing = listing
                except Exception as e:
                    st.error(f"Erreur lors de la génération : {e}")

        if cached_listing:
            st.subheader(cached_listing["title"])

            st.text_area(
                "Description (modifiable)",
                value=cached_listing["description"],
                height=200,
                key=f"desc_{listing_cache_key}",
            )

            price_col, tag_col = st.columns([1, 2])
            with price_col:
                st.metric(
                    label="Prix suggéré",
                    value=f"{cached_listing['suggested_price']:.2f} €",
                )
            with tag_col:
                st.write("**Tags :**")
                st.write("  ".join(f"`{t}`" for t in cached_listing.get("tags", [])))

            st.write("")
            copy_col, link_col = st.columns(2)
            with copy_col:
                st.code(
                    f"{cached_listing['title']}\n\n{cached_listing['description']}",
                    language=None,
                )
                st.caption("Sélectionnez le texte ci-dessus pour le copier.")
            with link_col:
                st.link_button(
                    f"📤 Créer l'annonce sur {PLATFORM_LABELS[selected_platform]}",
                    url=cached_listing["redirect_url"],
                    use_container_width=True,
                )

            if st.button("🔄 Régénérer", key=f"regen_{listing_cache_key}"):
                del st.session_state[listing_cache_key]
                st.rerun()

    # Cleanup temp files
    for path in (front_path, back_path):
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
