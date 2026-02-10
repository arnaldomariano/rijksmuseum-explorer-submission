# pages/🖼️_Compare_Artworks.py
"""
Compare Artworks — A/B comparison

Workflow:
1) In My Selection, mark up to 4 artworks as comparison candidates.
2) On this page, select exactly 2 items to compare.

Key rules:
- At most 2 selected in the comparison pair
- Do not modify widget session_state after widget instantiation (use callbacks)
- DEV_MODE is hidden by default; if enabled, shows raw Linked Art JSON
"""

from __future__ import annotations  # TEM que ser o primeiro import

import json
from typing import Any, Dict, List, Tuple

import streamlit as st

from ui_theme import inject_global_css, show_global_footer, show_page_intro
from app_paths import FAV_FILE
from analytics import track_event
from rijks_api import (
    get_best_image_url,
    fetch_metadata_by_objectnumber,
    RijksAPIError,
)

DEV_MODE = bool(st.secrets.get("DEV_MODE", False))

st.set_page_config(page_title="Compare Artworks", page_icon="🖼️", layout="wide")
st.set_page_config(
    page_title="Compare Artworks",
    page_icon="🖼️",
    layout="wide",
)

inject_global_css()

st.markdown(
    """
    <style>
    .stApp { background-color: #111111; color: #f5f5f5; }

    .cmp-card {
        background-color: #181818;
        border-radius: 12px;
        padding: 0.75rem 0.9rem 0.95rem 0.9rem;
        border: 1px solid #262626;
        box-shadow: 0 2px 10px rgba(0,0,0,0.45);
        transition: box-shadow 0.15s ease-out, border-color 0.15s ease-out, transform 0.10s ease-out;
    }
    .cmp-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(0,0,0,0.65);
    }
    .cmp-card-selected {
        border-color: #ffb347;
        box-shadow: 0 0 0 1px #ffb347, 0 6px 22px rgba(0,0,0,0.9);
        background: radial-gradient(circle at top left, #272015 0, #181818 55%);
    }
    .cmp-card-header {
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #b7b7b7;
        margin-bottom: 0.35rem;
    }
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


# ============================================================
# Data helpers
# ============================================================
def load_favorites_from_disk() -> Dict[str, Any]:
    if FAV_FILE.exists():
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def get_compare_candidates(favorites: Dict[str, Any]) -> List[str]:
    return [
        obj_id
        for obj_id, art in favorites.items()
        if isinstance(art, dict) and art.get("_compare_candidate")
    ]


@st.cache_data(show_spinner=False)
def cached_fetch_metadata(object_number: str) -> dict:
    return fetch_metadata_by_objectnumber(object_number)


# ============================================================
# Page header
# ============================================================
show_page_intro(
    "This page lets you compare artworks side by side using your current selection.",
    [
        "Uses artworks previously marked as comparison candidates in **My Selection**.",
        "Displays up to 4 artworks at the same time for side-by-side inspection.",
        "Shows high-level metadata (title, artist, date, object number, web link).",
        "Highlights whether each artwork has research notes in your local files.",
        "Can be used as a compact presentation view during research discussions.",
    ],
)

st.markdown("## 🖼️ Compare Artworks")
st.caption("1) Mark up to **4 candidates** in **My Selection** · 2) Select **exactly 2** below · 3) Scroll for side-by-side comparison.")


# ============================================================
# Load favorites
# ============================================================
if "favorites" not in st.session_state:
    st.session_state["favorites"] = load_favorites_from_disk()

favorites: Dict[str, Any] = st.session_state.get("favorites", {})
if not isinstance(favorites, dict) or not favorites:
    st.warning("No saved selection found. Go to the Explorer page and add artworks first.")
    st.stop()


# ============================================================
# Candidate list
# ============================================================
candidate_ids = get_compare_candidates(favorites)
if not candidate_ids:
    st.info("No comparison candidates marked. Go to **My Selection** and mark up to 4 items for comparison.")
    st.stop()

candidate_arts: List[Tuple[str, Dict[str, Any]]] = [(obj_id, favorites[obj_id]) for obj_id in candidate_ids if obj_id in favorites]


# ============================================================
# Pair selection state (max 2) — callback-safe
# ============================================================
if "cmp_pair_ids" not in st.session_state:
    st.session_state["cmp_pair_ids"] = candidate_ids[:2]
    for obj_id in candidate_ids:
        st.session_state[f"cmp_pair_{obj_id}"] = obj_id in st.session_state["cmp_pair_ids"]


def on_pair_toggle(changed_id: str) -> None:
    """Enforce a maximum of 2 selected items (safe inside widget callback)."""
    selected = [x for x in candidate_ids if bool(st.session_state.get(f"cmp_pair_{x}", False))]
    if len(selected) > 2:
        st.session_state[f"cmp_pair_{changed_id}"] = False
        st.session_state["cmp_pair_warning"] = True

    selected = [x for x in candidate_ids if bool(st.session_state.get(f"cmp_pair_{x}", False))]
    st.session_state["cmp_pair_ids"] = selected[:2]


# ============================================================
# Candidate cards
# ============================================================
st.markdown("### Candidates")

cols = st.columns(len(candidate_arts))
for col, (obj_id, art) in zip(cols, candidate_arts):
    is_selected = obj_id in (st.session_state.get("cmp_pair_ids", []) or [])
    card_classes = "cmp-card" + (" cmp-card-selected" if is_selected else "")

    with col:
        st.markdown(f'<div class="{card_classes}">', unsafe_allow_html=True)
        st.markdown('<div class="cmp-card-header">CANDIDATE</div>', unsafe_allow_html=True)

        img_url = get_best_image_url(art)
        if img_url:
            st.image(img_url, use_container_width=True)
        else:
            st.caption("No public image available in current mapping.")

        st.markdown(f'<div class="rijks-card-title">{art.get("title", "Untitled")}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="rijks-card-caption">{art.get("principalOrFirstMaker", "Unknown artist")}</div>', unsafe_allow_html=True)
        st.markdown(f'<span class="cmp-card-objectid">{obj_id}</span>', unsafe_allow_html=True)

        st.checkbox(
            "Include in comparison pair",
            key=f"cmp_pair_{obj_id}",
            on_change=on_pair_toggle,
            kwargs={"changed_id": obj_id},
        )

        st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.pop("cmp_pair_warning", False):
    st.warning("Please keep exactly 2 artworks selected for comparison.")


# ============================================================
# Side-by-side comparison
# ============================================================
st.markdown("---")
st.markdown("### 🔍 Side-by-side comparison")

pair_ids: List[str] = st.session_state.get("cmp_pair_ids", []) or []
if len(pair_ids) < 2:
    st.info("Select two artworks above to see the side-by-side comparison.")
    st.stop()

id_a, id_b = pair_ids[:2]
art_a = favorites.get(id_a)
art_b = favorites.get(id_b)

if not art_a or not art_b:
    st.error("Could not retrieve both artworks for comparison.")
    st.stop()

track_event(event="compare_clicked", page="Compare", props={"object_id_a": id_a, "object_id_b": id_b})

if DEV_MODE:
    with st.expander("DEV: Raw Linked Art JSON (A/B)", expanded=False):
        try:
            st.json({"A": cached_fetch_metadata(id_a), "B": cached_fetch_metadata(id_b)})
        except RijksAPIError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Unexpected error: {e}")

col_a, col_b = st.columns(2)

def render_side(label: str, obj_id: str, art: Dict[str, Any], container) -> None:
    with container:
        st.subheader(label)

        img_url = get_best_image_url(art)
        if img_url:
            st.image(img_url, use_container_width=True)
        else:
            st.caption("No public image available in current mapping.")

        st.write(f"**Title:** {art.get('title', 'Untitled')}")
        st.write(f"**Artist:** {art.get('principalOrFirstMaker', 'Unknown artist')}")

        dating = art.get("dating", {}) or {}
        date = dating.get("presentingDate") or dating.get("year")
        if date:
            st.write(f"**Date:** {date}")

        st.write(f"**Object ID:** `{obj_id}`")

        link = (art.get("links") or {}).get("web")
        if link:
            st.markdown(f"[View on Rijksmuseum website]({link})")

render_side("Artwork A", id_a, art_a, col_a)
render_side("Artwork B", id_b, art_b, col_b)

# ============================================================
# Footer
# ============================================================
show_global_footer()