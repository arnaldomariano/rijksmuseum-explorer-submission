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
from typing import Any, Dict, List, Tuple

import streamlit as st

from app_paths import FAV_FILE, NOTES_FILE, HERO_IMAGE_PATH
from analytics import track_event, track_event_once
from rijks_api import search_artworks, extract_year, get_best_image_url


# ============================================================
# Page config
# ============================================================
st.set_page_config(page_title="Rijksmuseum Explorer", page_icon="🎨", layout="wide")


# ============================================================
# Styling & footer
# ============================================================
def inject_custom_css() -> None:
    """Inject dark theme and card styling for the Explorer page."""
    st.markdown(
        """
        <style>
        .stApp { background-color: #111111; color: #f5f5f5; }
        div.block-container { max-width: 1200px; padding-top: 1.5rem; padding-bottom: 3rem; }

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
    """Filter based on the `_attribution` tag produced by rijks_api.py."""
    tag = (art.get("_attribution") or "unknown").lower()

    if auth_scope.startswith("Direct + Attributed"):
        return tag in ("direct", "attributed")
    if auth_scope.startswith("Direct only"):
        return tag == "direct"
    if auth_scope.startswith("Include workshop"):
        return tag in ("direct", "attributed", "workshop", "circle", "after")
    return True  # show all


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


# ============================================================
# Session init
# ============================================================
load_favorites()
favorites: Dict[str, Any] = st.session_state.setdefault("favorites", {})

load_notes()
notes: Dict[str, str] = st.session_state.setdefault("notes", {})

st.session_state.setdefault("results_full", [])     # full fetched results (after search)
st.session_state.setdefault("results_filtered", []) # filtered results (authorship + year/material/place)
st.session_state.setdefault("search_meta", {})       # meta about last run

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

# --- Search term ---
sidebar.subheader("Search")
search_term = sidebar.text_input("Search term", value="Rembrandt", help="Artist, title keyword, theme, etc.")

# --- Basic filters ---
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

# --- Fetch limit (how many items we retrieve from Data Services) ---
sidebar.subheader("Fetch limit")
fetch_limit = sidebar.slider(
    "Fetch up to",
    min_value=30,
    max_value=120,
    value=90,
    step=10,
    help="How many items to fetch from Data Services before local pagination.",
)

# --- Research scope (authorship) ---
sidebar.subheader("Research scope")
auth_scope = sidebar.selectbox(
    "Authorship scope",
    options=[
        "Direct + Attributed (recommended)",
        "Direct only",
        "Include workshop/circle/after",
        "Show all (including unknown)",
    ],
    index=0,
)
if auth_scope.startswith("Direct only"):
    sidebar.info("Showing only works with direct authorship. Attributed works are hidden.")

# --- Advanced filters (year range) ---
sidebar.subheader("Advanced filters")
year_min, year_max = sidebar.slider("Year range (approx.)", 1500, 2025, (1600, 1900), step=10)
sidebar.caption("Year filter is applied locally after results are fetched.")

# --- Text filters (materials / production places) ---
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

# --- Local pagination controls ---
sidebar.subheader("Pagination (local)")
per_page = sidebar.selectbox("Results per page", options=[12, 24, 30], index=0)
page_num = sidebar.number_input("Page", min_value=1, value=1, step=1)

# --- Run search ---
sidebar.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
run_search = sidebar.button("🔍 Apply filters & search", use_container_width=True)


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
                raw_results, total_found = search_artworks(
                    query=search_term.strip(),
                    page_size=int(fetch_limit),
                    sort=sort_by,
                    object_type=object_type_param,
                )

            # Store full fetched results
            st.session_state["results_full"] = raw_results or []

            # Apply local filters (authorship scope + metadata)
            filtered = [
                art for art in (raw_results or [])
                if passes_authorship_scope(art, auth_scope)
                and passes_metadata_filters(art, year_min, year_max, material_filter, place_filter)
            ]
            st.session_state["results_filtered"] = filtered

            # Store meta
            st.session_state["search_meta"] = {
                "api_count": len(raw_results or []),
                "filtered_count": len(filtered),
                "fetch_limit": int(fetch_limit),
                "auth_scope": auth_scope,
                "per_page": int(per_page),
            }

            # Analytics
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

# Use filtered results for display
filtered_results: List[Dict[str, Any]] = st.session_state.get("results_filtered", [])

# Local pagination over filtered set
total_filtered = len(filtered_results)
max_pages = max(1, ceil(total_filtered / int(per_page))) if per_page else 1
page_num = min(int(page_num), max_pages)

start_idx = (page_num - 1) * int(per_page)
end_idx = start_idx + int(per_page)
page_items = filtered_results[start_idx:end_idx]

# UI caption
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
        add_all_clicked = st.button("⭐ Add ALL on this page", use_container_width=True, key="btn_add_all_page")

    with col_remove:
        remove_all_clicked = st.button("🗑️ Remove ALL on this page", use_container_width=True, key="btn_remove_all_page")

    if add_all_clicked:
        added = 0
        for art in page_items:
            obj_num = art.get("objectNumber")
            if not obj_num:
                continue
            if obj_num not in favorites:
                favorites[obj_num] = art
                added += 1
                track_event(event="artwork_view", page="Explorer", props={"object_id": obj_num, "artist": art.get("principalOrFirstMaker", "Unknown artist"), "source": "selection_add_all_page"})
            st.session_state[f"fav_{obj_num}"] = True

        st.session_state["favorites"] = favorites
        save_favorites()
        saved_pill_placeholder.markdown(f'<div class="rijks-summary-pill">Saved artworks: <strong>{len(favorites)}</strong></div>', unsafe_allow_html=True)
        st.success(f"Added {added} artwork(s) to your selection." if added else "All items on this page were already in your selection.")

    if remove_all_clicked:
        removed = 0
        for art in page_items:
            obj_num = art.get("objectNumber")
            if not obj_num:
                continue
            if obj_num in favorites:
                favorites.pop(obj_num)
                removed += 1
            st.session_state[f"fav_{obj_num}"] = False

        st.session_state["favorites"] = favorites
        save_favorites()
        saved_pill_placeholder.markdown(f'<div class="rijks-summary-pill">Saved artworks: <strong>{len(favorites)}</strong></div>', unsafe_allow_html=True)
        st.success(f"Removed {removed} artwork(s) from your selection." if removed else "None of the items on this page were in your selection.")


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
                title = art.get("title", "Untitled")
                maker = art.get("principalOrFirstMaker", "Unknown artist")
                web_link = (art.get("links") or {}).get("web")

                note_text = notes.get(object_number, "") if object_number else ""
                has_notes = isinstance(note_text, str) and note_text.strip() != ""

                # Image
                img_url = get_best_image_url(art)
                if img_url:
                    try:
                        st.image(img_url, use_container_width=True)
                    except Exception:
                        st.markdown(
                            """
                            <div class="rijks-no-image-msg">
                            The image for this artwork could not be loaded at this moment.<br>
                            You can still open it on the Rijksmuseum website using the link below.
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(
                        """
                        <div class="rijks-no-image-msg">
                        No public image is available for this artwork via the current mapping.<br>
                        You can still open it on the Rijksmuseum website using the link below.
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown(f'<div class="rijks-card-title">{title}</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="rijks-card-caption">{maker}</div>', unsafe_allow_html=True)

                # Selection checkbox
                if object_number:
                    was_fav = object_number in favorites
                    checked = st.checkbox("In my selection", value=was_fav, key=f"fav_{object_number}")

                    if checked != was_fav:
                        if checked:
                            favorites[object_number] = art
                            track_event(event="selection_add_item", page="Explorer", props={"object_id": object_number, "artist": maker, "source": "Explorer"})
                        else:
                            favorites.pop(object_number, None)
                            track_event(event="selection_remove_item", page="Explorer", props={"object_id": object_number, "artist": maker, "source": "Explorer"})

                        st.session_state["favorites"] = favorites
                        save_favorites()
                        saved_pill_placeholder.markdown(f'<div class="rijks-summary-pill">Saved artworks: <strong>{len(favorites)}</strong></div>', unsafe_allow_html=True)

                    is_fav = checked
                else:
                    is_fav = False

                # Badges
                badge_parts: List[str] = []
                if is_fav:
                    badge_parts.append('<span class="rijks-badge rijks-badge-primary">⭐ In my selection</span>')
                if has_notes:
                    badge_parts.append('<span class="rijks-badge rijks-badge-secondary">📝 Notes</span>')
                badge_parts.append(attribution_badge_html(art))

                st.markdown('<div class="rijks-badge-row">' + " ".join(badge_parts) + "</div>", unsafe_allow_html=True)

                # Basic metadata
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
show_footer()