# 🏠_Home.py
"""
Rijksmuseum Explorer — Explorer page (online, Data Services)

This page provides:
- Search against Rijksmuseum Data Services (Search API)
- Results dereferenced via Linked Art resolver (handled in rijks_api.py)
- Research-friendly authorship scope filter via `_attribution`
- Local post-filters: year range + material/place substring filters
- Local pagination over the filtered set (honest: not remote paging)
- Results grid with artwork cards
- Global selection ("favorites") persisted locally
"""

from __future__ import annotations

import json
from math import ceil
from typing import Any, Dict, List

import streamlit as st

from app_paths import FAV_FILE, NOTES_FILE, HERO_IMAGE_PATH
from analytics import track_event, track_event_once
from rijks_api import (
    search_artworks,
    extract_year,
    get_best_image_url,
    probe_image_url,
    fetch_metadata_by_objectnumber,
    RijksAPIError,
)
from ui_theme import inject_global_css, show_global_footer, show_page_intro

# ============================================================
# Page config
# ============================================================
st.set_page_config(page_title="Rijksmuseum Explorer", page_icon="🎨", layout="wide")

st.set_page_config(
    page_title="Rijksmuseum Explorer",
    page_icon="🏛️",
    layout="wide",
)

inject_global_css()

# daqui pra frente continua tudo igual (show_page_intro, etc.)
# ============================================================
# Styling & footer
# ============================================================
def inject_custom_css() -> None:
    """Inject dark theme and card styling for the Explorer page."""
    st.markdown(
        """
        <style>
        .stApp { background-color: #111111; color: #f5f5f5; }
        div.block-container {
        max-width: 1200px;
        padding-top: 2.5rem;   /* <= mexa aqui até alinhar com as outras páginas */
        padding-bottom: 3rem;
         }

        section[data-testid="stSidebar"] { background-color: #181818 !important; }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] label { color: #f5f5f5 !important; }

        div[data-testid="stMarkdownContainer"] a { color: #ff9900 !important; text-decoration: none; }
        div[data-testid="stMarkdownContainer"] a:hover { text-decoration: underline; }

        .rijks-hero {
            border-radius: 14px;
            overflow: hidden;
            box-shadow: 0 4px 18px rgba(0,0,0,0.6);
            margin-bottom: 0.85rem;
        }

        .rijks-summary-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background-color: #262626;
            color: #f5f5f5;
            font-size: 0.85rem;
            margin-top: 0.35rem;
            margin-bottom: 1.0rem;
        }
        .rijks-summary-pill strong { color: #ff9900; }

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
            height: 260px;
            object-fit: cover;
            border-radius: 8px;
        }
        .rijks-card-title {
            font-size: 1rem;
            font-weight: 600;
            margin-top: 0.35rem;
            margin-bottom: 0.1rem;
            min-height: 1.3rem;
        }
        .rijks-card-caption { font-size: 0.9rem; color: #c7c7c7; margin-bottom: 0.25rem; }

        .rijks-badge-row { margin-top: 0.15rem; margin-bottom: 0.35rem; }
        .rijks-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.73rem;
            margin-right: 0.25rem;
            background-color: #262626;
            color: #f5f5f5;
            border: 1px solid #333333;
        }
        .rijks-badge-primary { background-color: #ff9900; color: #111111; border-color: #ff9900; }
        .rijks-badge-secondary { background-color: #262626; color: #ffddaa; border-color: #444444; }

        .rijks-no-image-msg {
            font-size: 0.8rem;
            color: #cccccc;
            background-color: #202020;
            border-radius: 8px;
            padding: 0.45rem 0.55rem;
            margin-top: 0.25rem;
            border: 1px dashed #444444;
        }

        .rijks-footer {
            margin-top: 2.5rem;
            padding-top: 0.75rem;
            border-top: 1px solid #262626;
            font-size: 0.8rem;
            color: #aaaaaa;
            text-align: center;
        }

        .stButton > button { border-radius: 999px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

show_page_intro(
    "Welcome to the Rijksmuseum Explorer research app. This homepage gives you a quick overview of what you can do:",
    [
        "Search and browse artworks from the Rijksmuseum collection.",
        "Build a personal research selection and keep it locally on this device.",
        "Compare up to 4 artworks side-by-side for visual and contextual analysis.",
        "Export your selection to CSV / JSON / PDF for further study.",
        "Keep all research activity local: favorites, notes and basic usage counts stay on this device only — nothing is sent to external servers.",
    ],
)

def show_footer() -> None:
    """Footer acknowledging Rijksmuseum Data Services."""
    st.markdown(
        """
        <div class="rijks-footer">
            Rijksmuseum Explorer — prototype created for study & research purposes.<br>
            Data & images provided by the Rijksmuseum Data Services (Linked Data / Linked Art).
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()


# ============================================================
# Local persistence: favorites + notes
# ============================================================
@st.cache_data(show_spinner=False)
def _read_json_file(path_str: str) -> dict:
    """Read JSON file safely (returns dict or {})."""
    try:
        with open(path_str, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_favorites() -> None:
    """Load favorites into session_state from disk."""
    if "favorites" not in st.session_state:
        st.session_state["favorites"] = _read_json_file(str(FAV_FILE)) if FAV_FILE.exists() else {}


def load_notes() -> None:
    """Load notes into session_state from disk."""
    if "notes" not in st.session_state:
        st.session_state["notes"] = _read_json_file(str(NOTES_FILE)) if NOTES_FILE.exists() else {}


def save_favorites() -> None:
    """Persist favorites to disk."""
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(st.session_state["favorites"], f, ensure_ascii=False, indent=2)
        _read_json_file.clear()
    except Exception:
        pass


# ============================================================
# Filtering helpers
# ============================================================
def passes_authorship_scope(art: Dict[str, Any], auth_scope: str) -> bool:
    """
    Filter artworks by authorship scope.

    Note:
    - Many objects still come with `_attribution="unknown"`.
    - To avoid hiding everything, most scopes keep "unknown".
    """
    tag = (art.get("_attribution") or "unknown").lower()

    if auth_scope.startswith("Direct only"):
        return tag in ("direct", "unknown")

    if auth_scope.startswith("Direct + Attributed + Circle"):
        return tag in ("direct", "attributed", "circle", "unknown")

    if auth_scope.startswith("Direct + Attributed"):
        return tag in ("direct", "attributed", "unknown")

    if auth_scope.startswith("Include workshop"):
        return tag in ("direct", "attributed", "workshop", "circle", "after", "unknown")

    if auth_scope.startswith("Show all"):
        return True

    return True

def passes_metadata_filters(
    art: Dict[str, Any],
    year_min: int,
    year_max: int,
    material_filter: str,
    place_filter: str,
) -> bool:
    """Local post-filters applied after results are fetched."""
    dating = art.get("dating") or {}
    year = extract_year(dating)

    if year is not None and (year < year_min or year > year_max):
        return False

    if material_filter:
        materials = art.get("materials") or []
        if material_filter.lower() not in ", ".join(materials).lower():
            return False

    if place_filter:
        places = art.get("productionPlaces") or []
        if place_filter.lower() not in ", ".join(places).lower():
            return False

    return True


def attribution_badge_html(art: Dict[str, Any]) -> str:
    """Return HTML badge for attribution label."""
    attr = (art.get("_attribution") or "unknown").lower()
    label_map = {
        "direct": "✅ Direct",
        "attributed": "🟡 Attributed",
        "workshop": "🟠 Workshop",
        "circle": "🔵 Circle/School",
        "after": "🟣 After",
        "unknown": "⚪ Unknown",
    }
    label = label_map.get(attr, "⚪ Unknown")
    return f'<span class="rijks-badge">{label}</span>'


def render_image_message(img_status: str) -> None:
    """Show the correct message box for missing/unavailable images."""

    if img_status == "copyright":
        st.markdown(
            """
            <div class="rijks-no-image-msg">
            This image cannot be displayed here due to copyright restrictions.<br>
            You can try opening it on the Rijksmuseum website, but it may also be unavailable there.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if img_status == "page_missing":
        st.markdown(
            """
            <div class="rijks-no-image-msg">
            The public Rijksmuseum page for this object appears to be unavailable (page not found).<br>
            The object may have moved or the link may be outdated.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if img_status == "broken":
        st.markdown(
            """
            <div class="rijks-no-image-msg">
            The image for this artwork could not be loaded at this moment.<br>
            You can still open it on the Rijksmuseum website using the link below.
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # default
    st.markdown(
        """
        <div class="rijks-no-image-msg">
        No public image is available for this artwork via the current mapping.<br>
        You can still open it on the Rijksmuseum website using the link below.
        </div>
        """,
        unsafe_allow_html=True,
    )


def image_status_badge_html(img_status: str) -> str:
    img_status = (img_status or "").lower()
    if img_status == "copyright":
        return '<span class="rijks-badge rijks-badge-secondary">🔒 Copyright</span>'
    if img_status == "page_missing":
        return '<span class="rijks-badge rijks-badge-secondary">⚠️ Page missing</span>'
    if img_status == "broken":
        return '<span class="rijks-badge rijks-badge-secondary">⚠️ Image unavailable</span>'
    if img_status == "no_public_image":
        return '<span class="rijks-badge rijks-badge-secondary">🚫 No public image</span>'
    return ""

def work_kind_badge_html(kind: str) -> str:
    k = (kind or "").lower()
    if k == "original":
        return '<span class="rijks-badge rijks-badge-secondary">🖼️ Original work</span>'
    if k == "reproduction":
        return '<span class="rijks-badge rijks-badge-secondary">🎞️ Reproduction</span>'
    if k == "photograph":
        return '<span class="rijks-badge rijks-badge-secondary">📷 Photograph</span>'
    return ""


# ============================================================
# Session init
# ============================================================
load_favorites()
favorites: Dict[str, Any] = st.session_state.setdefault("favorites", {})

load_notes()
notes: Dict[str, str] = st.session_state.setdefault("notes", {})

st.session_state.setdefault("results_full", [])
st.session_state.setdefault("results_filtered", [])

# garante que sempre exista um max_pages pelo menos 1
if "search_meta" not in st.session_state:
    st.session_state["search_meta"] = {"max_pages": 1}

track_event_once(
    event="page_view",
    page="Explorer",
    once_key="page_view::Explorer",
    props={"has_favorites": bool(favorites), "favorites_count": len(favorites)},
)


# ============================================================
# Sidebar UI
# ============================================================
sidebar = st.sidebar
sidebar.header("🧭 Explore & Filter")

with st.sidebar:
    st.markdown(
        '<div class="rijks-sidebar-main-title">🏠 Home</div>',
        unsafe_allow_html=True,
    )
    # resto dos controles da sidebar...

sidebar.subheader("Search")
search_term = sidebar.text_input("Search term", value="Rembrandt", help="Artist, title keyword, theme, etc.")

sidebar.subheader("Basic filters")
object_type = sidebar.selectbox(
    "Object type",
    options=["Any", "painting", "print", "drawing", "sculpture", "photo", "other"],
    help="High-level category hint (mapping coverage varies).",
)
object_type_param = None if object_type == "Any" else object_type

sort_label = sidebar.selectbox(
    "Sort results by",
    options=["Relevance (default)", "Artist name (A–Z)", "Date (oldest → newest)", "Date (newest → oldest)"],
)
sort_map = {
    "Relevance (default)": "relevance",
    "Artist name (A–Z)": "artist",
    "Date (oldest → newest)": "chronologic",
    "Date (newest → oldest)": "achronologic",
}
sort_by = sort_map[sort_label]

sidebar.subheader("Fetch limit")
fetch_limit = sidebar.slider(
    "Fetch up to",
    min_value=30,
    max_value=120,
    value=30,
    step=10,
    help="How many items to fetch from Data Services before local pagination.",
)

sidebar.subheader("Research scope")
auth_scope = sidebar.selectbox(
    "Authorship scope",
    options=[
        "Direct + Attributed (recommended)",
        "Direct + Attributed + Circle (A+C)",
        "Direct only",
        "Include workshop/circle/after",
        "Show all (including unknown)",
    ],
    index=2,  # se quiser manter "Direct only" como default, ajuste o index
)
if auth_scope.startswith("Direct + Attributed + Circle"):
    sidebar.info("Including direct, attributed and circle/school (plus unknown). Excludes workshop and after.")

sidebar.subheader("Advanced filters")
year_min, year_max = sidebar.slider("Year range (approx.)", 1500, 2025, (1600, 1900), step=10)
sidebar.caption("Year filter is applied locally after results are fetched.")

# ------------------------
# Text filters (helper explanation)
# ------------------------
sidebar.markdown(
    """
**Text filters (helper)**  

Text filters search inside the textual metadata of each artwork (title, long
title, description and notes returned by the API).

Use short keywords, for example:

- `self-portrait`
- `landscape`
- `night watch`
- `religious`
"""
)


sidebar.subheader("Text filters (optional)")
sidebar.caption("Material/place filters depend on metadata availability in the current mapping.")

material_presets = ["(any)", "oil on canvas", "paper", "wood", "ink", "etching", "bronze", "silver", "porcelain"]
material_choice = sidebar.selectbox("Material contains", options=material_presets + ["Custom…"])
if material_choice == "(any)":
    material_filter = ""
elif material_choice == "Custom…":
    material_filter = sidebar.text_input("Custom material filter", value="")
else:
    material_filter = material_choice

place_presets = [
    "(any)", "Amsterdam", "Haarlem", "Delft", "Utrecht", "The Hague", "Rotterdam", "Leiden",
    "Antwerp", "Paris", "London", "Italy", "Germany", "Brazil",
]
place_choice = sidebar.selectbox("Production place contains", options=place_presets + ["Custom…"])
if place_choice == "(any)":
    place_filter = ""
elif place_choice == "Custom…":
    place_filter = sidebar.text_input("Custom production place filter", value="")
else:
    place_filter = place_choice

sidebar.subheader("Pagination (local)")

# valores anteriores para manter estado entre reruns
prev_per_page = st.session_state.get("per_page", 12)
prev_page = int(st.session_state.get("page_num", 1))

# max_pages conhecido da última busca (ou 1 se nunca buscou)
max_pages_known = int(st.session_state.get("search_meta", {}).get("max_pages", 1))

per_page = sidebar.selectbox(
    "Results per page",
    options=[12, 24, 30],
    index=[12, 24, 30].index(prev_per_page) if prev_per_page in [12, 24, 30] else 0,
)
st.session_state["per_page"] = per_page

page_num = sidebar.number_input(
    "Page",
    min_value=1,
    max_value=max_pages_known,     # 👈 aqui some o '+' quando só há 1 página
    value=min(prev_page, max_pages_known),
    step=1,
)
st.session_state["page_num"] = int(page_num)

sidebar.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
run_search = sidebar.button("🔍 Apply filters & search", use_container_width=True)

# Pequeno lembrete sobre a seleção global (herdado da versão legacy)
sidebar.caption(
    "Artworks marked as **In my selection** remain saved across searches and sessions. "
    "If you do not want previous selections to appear pre-selected in new searches, "
    "clear your selection on the **My Selection** page."
)

# ============================================================
# Main header
# ============================================================
st.markdown("### 🎨 Rijksmuseum Explorer")

if HERO_IMAGE_PATH.exists():
    st.markdown('<div class="rijks-hero">', unsafe_allow_html=True)
    st.image(str(HERO_IMAGE_PATH), use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

st.write(
    "Explore artworks from the Rijksmuseum collection using the Data Services (Linked Data). "
    "Use the sidebar to search and filter, then browse results below."
)

st.caption(
    "Tip: use the checkbox **“In my selection”** in each card to build your personal selection. "
    "You can then review, compare and export it on the **My Selection** page."
)

with st.expander("ℹ️ How the search works (quick guide)", expanded=False):
    st.markdown(
        """
- **Search term** → queried in the Rijksmuseum **Data Services Search API**
- **Results** → dereferenced via the **Linked Art resolver** (Linked Data)
- **Fetch limit** → how many items we retrieve before local pagination
- **Pagination** → local paging over the filtered result set
        """
    )

saved_pill_placeholder = st.empty()
saved_pill_placeholder.markdown(
    f'<div class="rijks-summary-pill">Saved artworks: <strong>{len(favorites)}</strong></div>',
    unsafe_allow_html=True,
)


# ============================================================
# Search execution
# ============================================================
if run_search:
    if not search_term.strip():
        st.warning("Please enter a search term before running the search.")
        st.session_state["results_full"] = []
        st.session_state["results_filtered"] = []
        st.session_state["search_meta"] = {}
    else:
        try:
            with st.spinner("Fetching artworks from Rijksmuseum Data Services..."):
                raw_results, _total_found = search_artworks(
                    query=search_term.strip(),
                    page_size=int(fetch_limit),
                    sort=sort_by,
                    object_type=object_type_param,
                )

            st.session_state["results_full"] = raw_results or []

            filtered = [
                art for art in (raw_results or [])
                if passes_authorship_scope(art, auth_scope)
                and passes_metadata_filters(art, year_min, year_max, material_filter, place_filter)
            ]
            st.session_state["results_filtered"] = filtered

            st.session_state["search_meta"] = {
                "api_count": len(raw_results or []),
                "filtered_count": len(filtered),
                "fetch_limit": int(fetch_limit),
                "auth_scope": auth_scope,
                "per_page": int(per_page),
            }

            track_event(
                event="search_executed",
                page="Explorer",
                props={
                    "query_sample": search_term.strip()[:60],
                    "query_length": len(search_term.strip()),
                    "object_type": object_type_param or "Any",
                    "sort_by": sort_by,
                    "fetch_limit": int(fetch_limit),
                    "auth_scope": auth_scope,
                    "year_min": year_min,
                    "year_max": year_max,
                    "has_material_filter": bool(material_filter),
                    "has_place_filter": bool(place_filter),
                    "api_returned": len(raw_results or []),
                    "filtered_count": len(filtered),
                },
            )

        except Exception as e:
            st.error(f"Unexpected error while searching the Rijksmuseum online collection: {e}")
            st.session_state["results_full"] = []
            st.session_state["results_filtered"] = []
            st.session_state["search_meta"] = {}


filtered_results: List[Dict[str, Any]] = st.session_state.get("results_filtered", [])

total_filtered = len(filtered_results)
max_pages = max(1, ceil(total_filtered / int(per_page))) if per_page else 1

# clamp da página atual
page_num = min(int(page_num), max_pages)

# guarda no session_state para o próximo rerun
meta = st.session_state.get("search_meta", {})
meta["max_pages"] = max_pages
st.session_state["search_meta"] = meta
st.session_state["page_num"] = int(page_num)

start_idx = (page_num - 1) * int(per_page)
end_idx = start_idx + int(per_page)
page_items = filtered_results[start_idx:end_idx]

# ---------------------------------------
# Dedup: evita obras repetidas na página
# (e evita conflito de key na checkbox)
# ---------------------------------------
seen_ids = set()
dedup_items = []
for art in page_items:
    obj = art.get("objectNumber")
    # se não tiver ID, a gente deixa passar
    if not obj:
        dedup_items.append(art)
        continue
    # se já vimos esse ID, pula
    if obj in seen_ids:
        continue
    seen_ids.add(obj)
    dedup_items.append(art)

page_items = dedup_items
# ---------------------------------------

if total_filtered > 0:
    st.caption(
        f"Showing page **{page_num} / {max_pages}** — "
        f"**{len(page_items)}** item(s) on this page — "
        f"**{total_filtered}** item(s) after filters (fetched: {len(st.session_state.get('results_full', []))})."
    )
else:
    if st.session_state.get("results_full"):
        st.warning("Results were fetched, but none match your current filters. Try broadening scope and/or filters.")
    else:
        st.info("No artworks to display yet. Use the sidebar and click **Apply filters & search**.")


# ============================================================
# Bulk selection tools
# ============================================================
if page_items:
    st.markdown("### Selection tools (current page)")
    col_add, col_remove = st.columns(2)

    with col_add:
        add_all_clicked = st.button(
            "⭐ Add ALL on this page",
            use_container_width=True,
            key="btn_add_all_page",
        )
    with col_remove:
        remove_all_clicked = st.button(
            "🗑️ Remove ALL on this page",
            use_container_width=True,
            key="btn_remove_all_page",
        )

    # ADD ALL: força todas as obras desta página a entrarem na seleção
    if add_all_clicked:
        for art in page_items:
            obj_num = art.get("objectNumber")
            if not obj_num:
                continue

            # garante que está em favorites
            favorites[obj_num] = art
            # força o checkbox correspondente a ficar marcado
            st.session_state[f"fav_{obj_num}"] = True

        st.session_state["favorites"] = favorites
        save_favorites()
        saved_pill_placeholder.markdown(
            f'<div class="rijks-summary-pill">Saved artworks: '
            f'<strong>{len(favorites)}</strong></div>',
            unsafe_allow_html=True,
        )
        st.success("All artworks on this page were added to your selection.")
        st.rerun()

    # REMOVE ALL: força todas as obras desta página a saírem da seleção
    if remove_all_clicked:
        for art in page_items:
            obj_num = art.get("objectNumber")
            if not obj_num:
                continue

            # remove de favorites (se existir)
            favorites.pop(obj_num, None)
            # força o checkbox a ficar desmarcado
            st.session_state[f"fav_{obj_num}"] = False

        st.session_state["favorites"] = favorites
        save_favorites()
        saved_pill_placeholder.markdown(
            f'<div class="rijks-summary-pill">Saved artworks: '
            f'<strong>{len(favorites)}</strong></div>',
            unsafe_allow_html=True,
        )
        st.success("All artworks on this page were removed from your selection.")
        st.rerun()

@st.cache_data(show_spinner=False)
def _fetch_better_title(object_number: str) -> str | None:
    """
    Quando o resultado da busca só traz o objectNumber como 'title'
    (ou nada), tentamos buscar um título melhor na API de detalhe.

    Fica em cache para não bater na API toda hora.
    """
    if not object_number:
        return None

    try:
        detail = fetch_metadata_by_objectnumber(object_number)
    except (RijksAPIError, Exception):
        return None

    if not isinstance(detail, dict):
        return None

    art_obj = detail.get("artObject") or detail

    # Tentativas em ordem de preferência
    for key in ("titleEnglish", "title", "longTitle"):
        val = (art_obj.get(key) or "").strip()
        if val:
            return val

    return None

# ============================================================
# Results grid (cards)
# ============================================================
if page_items:
    cards_per_row = 3
    for start in range(0, len(page_items), cards_per_row):
        row = page_items[start:start + cards_per_row]
        cols = st.columns(len(row))

        for col, art in zip(cols, row):
            with col:
                st.markdown('<div class="rijks-card">', unsafe_allow_html=True)

                object_number = art.get("objectNumber")

                # ---------------------------------------
                # 1) Título (com fallback via detalhe)
                # ---------------------------------------
                raw_title = (art.get("title") or "").strip()
                long_title = (art.get("longTitle") or "").strip()
                obj_num_str = (object_number or "").strip()

                display_title = raw_title or long_title or "Untitled"

                # Se o "título" for só o ID ou estiver vazio,
                # tentamos buscar algo melhor via API de detalhe.
                if obj_num_str and (display_title == obj_num_str or display_title == "Untitled"):
                    better = _fetch_better_title(obj_num_str)
                    if better and better != obj_num_str:
                        display_title = better

                # ---------------------------------------
                # 2) Artista (normalizado)
                # ---------------------------------------
                raw_maker = art.get("principalOrFirstMaker", "")
                maker_norm = (raw_maker or "").strip()

                if maker_norm.lower() in (
                    "",
                    "unknown",
                    "unknown artist",
                    "onbekend",
                    "onbekende kunstenaar",
                    "n/a",
                    "niet vermeld",
                ):
                    maker = "Unknown artist"
                elif maker_norm.lower() in ("anonymous", "anoniem"):
                    maker = "anonymous"
                else:
                    maker = maker_norm

                web_link = (art.get("links") or {}).get("web")

                note_text = notes.get(object_number, "") if object_number else ""
                has_notes = isinstance(note_text, str) and note_text.strip() != ""

                # ---------------------------------------
                # 3) Imagem + status
                # ---------------------------------------
                img_url = get_best_image_url(art)
                status = (art.get("_image_status") or "no_public_image").lower()
                img_status = "no_public_image"

                if img_url:
                    probe = probe_image_url(img_url)
                    if probe.get("ok"):
                        img_status = "ok"
                        st.image(img_url, use_container_width=True)
                    else:
                        pstatus = (probe.get("status") or "").lower()
                        if pstatus == "copyright":
                            status = "copyright"
                        else:
                            status = "broken"

                if img_status != "ok":
                    render_image_message(status)

                # ---------------------------------------
                # 4) Título + artista no card
                # ---------------------------------------
                st.markdown(
                    f'<div class="rijks-card-title">{display_title}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="rijks-card-caption">{maker}</div>',
                    unsafe_allow_html=True,
                )

                # ---------------------------------------
                # 5) Checkbox "In my selection"
                #    (controlada só via session_state)
                # ---------------------------------------
                if object_number:
                    checkbox_key = f"fav_{object_number}"

                    # Inicializa o estado da checkbox uma única vez
                    if checkbox_key not in st.session_state:
                        st.session_state[checkbox_key] = object_number in favorites

                    # A partir daqui, quem manda é st.session_state[checkbox_key]
                    checked = st.checkbox(
                        "In my selection",
                        key=checkbox_key,
                    )

                    # Situação atual no "modelo de verdade"
                    was_fav = object_number in favorites

                    if checked != was_fav:
                        if checked:
                            favorites[object_number] = art
                            track_event(
                                event="selection_add_item",
                                page="Explorer",
                                props={
                                    "object_id": object_number,
                                    "artist": maker,
                                    "source": "Explorer",
                                },
                            )
                            track_event(
                                event="artwork_view",
                                page="Explorer",
                                props={
                                    "object_id": object_number,
                                    "artist": maker,
                                    "source": "selection_checkbox",
                                },
                            )
                        else:
                            favorites.pop(object_number, None)
                            track_event(
                                event="selection_remove_item",
                                page="Explorer",
                                props={
                                    "object_id": object_number,
                                    "artist": maker,
                                    "source": "Explorer",
                                },
                            )

                        st.session_state["favorites"] = favorites
                        save_favorites()
                        saved_pill_placeholder.markdown(
                            f'<div class="rijks-summary-pill">Saved artworks: '
                            f'<strong>{len(favorites)}</strong></div>',
                            unsafe_allow_html=True,
                        )

                    is_fav = checked
                else:
                    is_fav = False
                # ---------------------------------------
                # 6) Badges
                # ---------------------------------------
                badge_parts: List[str] = []

                if is_fav:
                    badge_parts.append(
                        '<span class="rijks-badge rijks-badge-primary">⭐ In my selection</span>'
                    )
                if has_notes:
                    badge_parts.append(
                        '<span class="rijks-badge rijks-badge-secondary">📝 Notes</span>'
                    )

                badge_parts.append(attribution_badge_html(art))

                if img_status != "ok":
                    badge = image_status_badge_html(status)
                    if badge:
                        badge_parts.append(badge)

                st.markdown(
                    '<div class="rijks-badge-row">' + " ".join(badge_parts) + "</div>",
                    unsafe_allow_html=True,
                )

                # ---------------------------------------
                # 7) Metadados básicos
                # ---------------------------------------
                dating = art.get("dating") or {}
                presenting_date = dating.get("presentingDate")
                year = extract_year(dating) if dating else None

                if presenting_date:
                    st.text(f"Date: {presenting_date}")
                elif year:
                    st.text(f"Year: {year}")

                if object_number:
                    st.text(f"Object ID: {object_number}")

                if web_link:
                    st.markdown(f"[View on Rijksmuseum website]({web_link})")

                st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# Footer
# ============================================================
show_global_footer()