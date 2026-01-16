import json

import streamlit as st

from app_paths import FAV_FILE
from rijks_api import get_best_image_url
from analytics import track_event


# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="Compare Artworks",
    page_icon="🖼️",
    layout="wide",
)


# ============================================================
# CSS helpers
# ============================================================
def inject_compare_css() -> None:
    """Add a subtle glow around artworks currently in the A/B pair."""
    st.markdown(
        """
        <style>
        /* Wrapper for each candidate card */
        .cmp-card {
            background-color: #181818;
            border-radius: 12px;
            padding: 0.75rem 0.9rem 0.95rem 0.9rem;
            border: 1px solid #262626;
            box-shadow: 0 2px 10px rgba(0,0,0,0.45);
            transition:
                box-shadow 0.15s ease-out,
                border-color 0.15s ease-out,
                transform 0.10s ease-out,
                background-color 0.15s ease-out;
        }

        .cmp-card:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.65);
        }

        /* Highlight for artworks that are in the current A/B pair */
        .cmp-card-selected {
            border-color: #ffb347;
            box-shadow:
                0 0 0 1px #ffb347,
                0 6px 22px rgba(0,0,0,0.9);
            background: radial-gradient(circle at top left, #272015 0, #181818 55%);
        }

        /* Small header line inside the card */
        .cmp-card-header {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #b7b7b7;
            margin-bottom: 0.35rem;
        }

        /* Object ID pill */
        .cmp-card-objectid {
            display: inline-block;
            margin-top: 0.4rem;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.78rem;
            background-color: #101010;
            border: 1px solid #333333;
            color: #a3e59f;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_custom_css() -> None:
    """Global layout + base card styling for this page."""
    st.markdown(
        """
        <style>
        /* Fundo escuro e texto claro, como no restante do app */
        .stApp { background-color: #111111; color: #f5f5f5; }

        /* Deixar o container central bem largo */
        div.block-container {
            max-width: 95vw;
            padding-left: 2rem;
            padding-right: 2rem;
            padding-top: 1.2rem;
            padding-bottom: 2.5rem;
        }

        @media (min-width: 1400px) {
            div.block-container {
                padding-left: 3rem;
                padding-right: 3rem;
            }
        }

        /* Cartão genérico no estilo Rijks (se usado aqui) */
        .rijks-card {
            background-color: #181818;
            border-radius: 12px;
            padding: 0.75rem 0.75rem 0.9rem 0.75rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 1px solid #262626;
            margin-bottom: 1rem;
            margin-top: 0.35rem;
        }

        .rijks-card img {
            width: 100%;
            height: 220px;
            object-fit: cover;
            border-radius: 8px;
        }

        .rijks-card-title {
            font-size: 0.95rem;
            font-weight: 600;
            margin-top: 0.5rem;
            margin-bottom: 0.15rem;
            color: #f1f1f1;
        }

        .rijks-card-caption {
            font-size: 0.8rem;
            color: #b8b8b8;
            margin-bottom: 0.25rem;
        }

        .rijks-compare-controls {
            background-color: #181818;
            border-radius: 12px;
            border: 1px solid #262626;
            padding: 0.8rem 1rem 1rem 1rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Data helpers
# ============================================================
def load_favorites_from_disk() -> dict:
    """Load favorites from the local JSON file if needed."""
    if FAV_FILE.exists():
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
                if isinstance(data, dict):
                    return data
        except Exception:
            return {}
    return {}


def get_compare_candidates_from_favorites(favorites: dict) -> list[str]:
    """Return objectNumbers marked as comparison candidates inside favorites."""
    return [
        obj_id
        for obj_id, art in favorites.items()
        if isinstance(art, dict) and art.get("_compare_candidate")
    ]


# ============================================================
# Page header
# ============================================================
inject_custom_css()
inject_compare_css()

st.markdown("## 🖼️ Compare Artworks")
st.caption(
    "1. Mark up to **4 candidates** in **My Selection** · "
    "2. Tick **exactly 2** below · "
    "3. Scroll for the side-by-side comparison."
)

# Optional flash message (used when clearing all marks)
flash_msg = st.session_state.pop("cmp_flash_message", None)
if flash_msg:
    st.success(flash_msg)


# ============================================================
# Load favorites + handle 'clear all marks' action from previous run
# ============================================================
if "favorites" not in st.session_state:
    st.session_state["favorites"] = load_favorites_from_disk()

favorites: dict = st.session_state.get("favorites", {})
if not isinstance(favorites, dict):
    favorites = {}

# If the user clicked "Clear comparison marks in My Selection" in the previous run,
# we handle it here *before* computing candidates or creating widgets.
clear_all_requested = st.session_state.pop("cmp_action_clear_all", False)
if clear_all_requested:
    changed = False
    for obj_id, art in list(favorites.items()):
        if isinstance(art, dict) and art.get("_compare_candidate"):
            art.pop("_compare_candidate", None)
            favorites[obj_id] = art
            changed = True

    if changed:
        st.session_state["favorites"] = favorites
        try:
            with open(FAV_FILE, "w", encoding="utf-8") as f:
                json.dump(favorites, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # Clear all local comparison state as well
    st.session_state["cmp_pair_ids"] = []
    for key in list(st.session_state.keys()):
        if key.startswith("cmp_pair_"):
            del st.session_state[key]
    st.session_state["compare_candidates"] = []

    # Store a small flash message for the next run and rerun immediately
    st.session_state["cmp_flash_message"] = (
        "All comparison marks were cleared. "
        "You can now mark new candidates in **My Selection**."
    )
    st.rerun()


# ============================================================
# Build candidate list from favorites
# ============================================================
if not favorites:
    st.warning(
        "You do not have any artworks in your selection yet. "
        "Go to the **Rijksmuseum Explorer** page, mark some artworks as "
        "**In my selection**, and then return here."
    )
    st.stop()

compare_candidates = get_compare_candidates_from_favorites(favorites)
st.session_state["compare_candidates"] = compare_candidates

if not compare_candidates:
    st.info(
        "No comparison candidates have been marked yet. "
        "Go to **My Selection**, mark up to **4 artworks** as "
        "*Mark for comparison (up to 4)*, and then come back to this page."
    )
    st.stop()

candidate_arts: list[tuple[str, dict]] = [
    (obj_id, favorites[obj_id])
    for obj_id in compare_candidates
    if obj_id in favorites
]
candidate_ids = [obj_id for obj_id, _ in candidate_arts]


# ============================================================
# Sync pair state (checkboxes <-> cmp_pair_ids)
# ============================================================
clear_pair_requested = st.session_state.pop("cmp_action_clear_pair", False)

if clear_pair_requested:
    # Clear the logical pair and all checkbox states for this run.
    st.session_state["cmp_pair_ids"] = []
    for obj_id in candidate_ids:
        key = f"cmp_pair_{obj_id}"
        st.session_state[key] = False
else:
    # Normal path: infer the pair from checkbox states (previous run) or defaults.
    existing_pair = st.session_state.get("cmp_pair_ids")

    # Collect raw checkbox states from the previous run, if any.
    raw_selected = [
        obj_id
        for obj_id in candidate_ids
        if bool(st.session_state.get(f"cmp_pair_{obj_id}", False))
    ]

    if existing_pair is None:
        # First time on this page in the current session.
        if raw_selected:
            pair_ids = raw_selected[:2]
        else:
            # Default: first two candidates (or fewer if < 2 available).
            pair_ids = candidate_ids[:2]
    else:
        # We already had a pair; we respect the current checkbox states.
        pair_ids = raw_selected[:2]

    st.session_state["cmp_pair_ids"] = pair_ids

    # Ensure checkbox states match the final pair_ids (max 2 items).
    for obj_id in candidate_ids:
        key = f"cmp_pair_{obj_id}"
        st.session_state[key] = obj_id in pair_ids

# Final pair IDs for this run (used by UI + comparison block)
current_pair_ids: list[str] = st.session_state.get("cmp_pair_ids", [])


# ============================================================
# Candidate thumbnails + checkboxes
# ============================================================
st.markdown("### Candidates from My Selection")

cols = st.columns(len(candidate_arts))
for col, (obj_id, art) in zip(cols, candidate_arts):
    # Is this artwork currently in the A/B pair?
    is_selected = obj_id in current_pair_ids

    # Base card classes + optional “selected” glow
    card_classes = "cmp-card"
    if is_selected:
        card_classes += " cmp-card-selected"

    with col:
        st.markdown(f'<div class="{card_classes}">', unsafe_allow_html=True)

        st.markdown(
            '<div class="cmp-card-header">CANDIDATE FROM MY SELECTION</div>',
            unsafe_allow_html=True,
        )

        img_url = get_best_image_url(art)
        if img_url:
            try:
                st.image(img_url, use_container_width=True)
            except Exception:
                st.write("Error displaying image.")
        else:
            st.caption("No public image available for this artwork via API.")

        title = art.get("title", "Untitled")
        maker = art.get("principalOrFirstMaker", "Unknown artist")
        dating = art.get("dating", {}) or {}
        date = dating.get("presentingDate") or dating.get("year")
        obj_label = obj_id

        st.markdown(
            f'<div class="rijks-card-title">{title}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="rijks-card-caption">{maker}</div>',
            unsafe_allow_html=True,
        )
        if date:
            st.caption(str(date))

        st.markdown(
            f'<span class="cmp-card-objectid">{obj_label}</span>',
            unsafe_allow_html=True,
        )

        checkbox_key = f"cmp_pair_{obj_id}"
        st.checkbox(
            "Include in comparison pair",
            key=checkbox_key,
        )

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Pair controls + comparison section
# ============================================================
st.markdown("---")
st.markdown("### Choose two artworks to compare")

num_selected = len(current_pair_ids)
st.write(f"Currently selected for comparison: **{num_selected}**")

with st.expander("Pair & comparison controls", expanded=(num_selected == 0)):
    with st.container():
        st.markdown('<div class="rijks-compare-controls">', unsafe_allow_html=True)
        col_btn_pair, col_btn_all = st.columns(2)

        with col_btn_pair:
            if st.button("Clear current pair (keep candidates)", key="btn_clear_pair"):
                st.session_state["cmp_action_clear_pair"] = True
                st.rerun()

        with col_btn_all:
            if st.button(
                "Clear comparison marks in My Selection",
                key="btn_clear_all_marks",
            ):
                st.session_state["cmp_action_clear_all"] = True
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

st.markdown("### 🔍 Side-by-side comparison")

if num_selected < 2:
    st.info(
        "Select two artworks above to see the side-by-side comparison. "
        "You can include or exclude artworks using the checkboxes under each candidate."
    )
elif num_selected > 2:
    st.warning("Please keep **exactly 2** artworks selected.")

else:
    # Exactly two artworks in the pair for this run.
    id_a, id_b = current_pair_ids
    art_a = favorites.get(id_a)
    art_b = favorites.get(id_b)

    if not art_a or not art_b:
        st.error("Could not retrieve both artworks for comparison.")
    else:
        track_event(
            event="compare_clicked",
            page="Compare",
            props={
                "object_id_a": id_a,
                "object_id_b": id_b,
            },
        )

        col_a, col_b = st.columns(2)

        def render_side(label: str, obj_id: str, art: dict, container):
            """Render one side of the comparison."""
            with container:
                st.subheader(label)
                img_url = get_best_image_url(art)
                if img_url:
                    try:
                        st.image(img_url, use_container_width=True)
                    except Exception:
                        st.write("Error displaying image.")
                else:
                    st.caption(
                        "No public image available for this artwork via API."
                    )

                title = art.get("title", "Untitled")
                maker = art.get("principalOrFirstMaker", "Unknown artist")
                dating = art.get("dating", {}) or {}
                date = dating.get("presentingDate") or dating.get("year")
                link = art.get("links", {}).get("web")

                st.write(f"**Title:** {title}")
                st.write(f"**Artist:** {maker}")
                if date:
                    st.write(f"**Date:** {date}")
                st.write(f"**Object ID:** `{obj_id}`")
                if link:
                    st.markdown(f"[View on Rijksmuseum website]({link})")

        render_side("Artwork A", id_a, art_a, col_a)
        render_side("Artwork B", id_b, art_b, col_b)