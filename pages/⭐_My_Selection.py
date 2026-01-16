import json
import io
import csv
import base64
from datetime import datetime
from textwrap import wrap

import requests
import streamlit as st

from app_paths import FAV_FILE, NOTES_FILE, PDF_META_FILE
from rijks_api import get_best_image_url
from analytics import track_event

"""
My Selection page

This page shows the user's saved artworks (local favorites). It provides:

- Local persistence of favorites and research notes (JSON files).
- Internal filters (metadata and notes) over the current selection.
- Gallery controls (sorting, grouping by artist, compact mode, pagination).
- Export tools (CSV / JSON / PDF, selection-sharing code, notes exports).
- Artwork comparison (side-by-side) within the current selection.
- Detail view for a single artwork with zoom and research notes editor.
- Local analytics events for usage statistics (no data is sent anywhere).
"""

# ============================================================
# ReportLab import (optional PDF generation with thumbnails)
# ============================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ============================================================
# Image URL cache helper
# ============================================================
@st.cache_data(show_spinner=False)
def cached_best_image_url(art: dict):
    """Small cache wrapper around get_best_image_url for faster gallery rendering."""
    return get_best_image_url(art)


# ============================================================
# PDF meta loader (shared with PDF_Setup page)
# ============================================================
def load_pdf_meta() -> dict:
    """
    Load PDF configuration used by this page and the PDF_Setup page.

    Structure:
        {
            "opening_text": "...",
            "include_cover": true,
            "include_opening_text": true,
            "include_notes": true,
            "include_comments": true,
            "artwork_comments": { "objectNumber": "text", ... }
        }

    Data is stored in a local JSON file and cached in session_state["pdf_meta"].
    """
    if "pdf_meta" in st.session_state:
        return st.session_state["pdf_meta"]

    base = {
        "opening_text": "",
        "include_cover": True,
        "include_opening_text": True,
        "include_notes": True,
        # Campos antigos (include_comments, artwork_comments) foram descontinuados.
    }
    if PDF_META_FILE.exists():
        try:
            with open(PDF_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    base.update(data)
        except Exception:
            # PDF meta is optional; never break the app because of it
            pass

    st.session_state["pdf_meta"] = base
    return base


# ============================================================
# Notes helpers (local JSON file)
# ============================================================
def load_notes() -> None:
    """Load research notes for artworks into st.session_state['notes']."""
    if "notes" in st.session_state:
        return

    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state["notes"] = data if isinstance(data, dict) else {}
        except Exception:
            st.session_state["notes"] = {}
    else:
        st.session_state["notes"] = {}


def save_notes() -> None:
    """Persist current notes from session_state to NOTES_FILE."""
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                st.session_state.get("notes", {}),
                f,
                ensure_ascii=False,
                indent=2,
            )
    except Exception:
        # Notes are a convenience feature; never break the app here
        pass


# ============================================================
# Selection statistics helper
# ============================================================
def compute_selection_stats(favorites_dict: dict) -> dict:
    """
    Compute basic statistics for a favorites dictionary:

    - count: number of artworks
    - artists: distinct artists
    - min_year / max_year: approximate date range
    """
    if not favorites_dict:
        return {"count": 0, "artists": 0, "min_year": None, "max_year": None}

    artworks = list(favorites_dict.values())
    artists = set()
    years: list[int] = []

    for art in artworks:
        maker = art.get("principalOrFirstMaker")
        if maker:
            artists.add(maker)

        dating = art.get("dating") or {}
        year = None

        # Prefer numeric year when available
        if isinstance(dating.get("year"), int):
            year = dating["year"]
        else:
            presenting_date = dating.get("presentingDate")
            if isinstance(presenting_date, str) and presenting_date[:4].isdigit():
                try:
                    year = int(presenting_date[:4])
                except Exception:
                    year = None

        if year is not None:
            years.append(year)

    return {
        "count": len(artworks),
        "artists": len(artists),
        "min_year": min(years) if years else None,
        "max_year": max(years) if years else None,
    }


# ============================================================
# Internal metadata filter helper (inside selection)
# ============================================================
def passes_selection_filters(
    art: dict,
    text_filter: str,
    year_min: int,
    year_max: int,
    artist_filter: str,
    object_type_filter: str,
) -> bool:
    """
    Return True if an artwork passes the internal metadata filters.

    Filters:
    - year range
    - free text (title / longTitle / maker / materials / techniques / places / types)
    - artist substring
    - object type substring
    """
    dating = art.get("dating") or {}
    year_val = None

    if isinstance(dating.get("year"), int):
        year_val = dating["year"]
    else:
        presenting_date = dating.get("presentingDate")
        if isinstance(presenting_date, str) and presenting_date[:4].isdigit():
            try:
                year_val = int(presenting_date[:4])
            except Exception:
                year_val = None

    if year_val is not None and not (year_min <= year_val <= year_max):
        return False

    # Free-text filter
    if text_filter:
        needle = text_filter.lower().strip()
        if needle:
            parts: list[str] = []

            for field in ("title", "longTitle", "principalOrFirstMaker"):
                value = art.get(field)
                if isinstance(value, str):
                    parts.append(value.lower())

            for field in ("materials", "techniques", "productionPlaces", "objectTypes"):
                values = art.get(field) or []
                if isinstance(values, list):
                    parts.extend(str(v).lower() for v in values)

            if needle not in " | ".join(parts):
                return False

    # Artist substring
    if artist_filter:
        artist = (art.get("principalOrFirstMaker") or "").lower()
        if artist_filter.lower().strip() not in artist:
            return False

    # Object type substring
    if object_type_filter:
        obj_types = art.get("objectTypes") or []
        if object_type_filter.lower().strip() not in ", ".join(obj_types).lower():
            return False

    return True


# ============================================================
# Custom CSS & footer
# ============================================================
def inject_custom_css() -> None:
    """Inject dark-mode layout and gallery card styling."""
    st.markdown(
        """
        <style>
        .stApp { background-color: #111111; color: #f5f5f5; }

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

        section[data-testid="stSidebar"] {
            background-color: #181818 !important;
        }

        h1, h2, h3 { font-weight: 600; }
        h2 { font-size: 1.5rem; margin-top: 0.5rem; margin-bottom: 0.75rem; }
        h3 { font-size: 1.15rem; margin-top: 1.25rem; margin-bottom: 0.5rem; }

        div[data-testid="stMarkdownContainer"] a {
            color: #ff9900 !important;
            text-decoration: none;
        }
        div[data-testid="stMarkdownContainer"] a:hover { text-decoration: underline; }

        .rijks-card {
            background-color: #181818;
            border-radius: 12px;
            padding: 0.75rem 0.75rem 0.9rem 0.75rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 1px solid #262626;
            margin-bottom: 1rem;
            margin-top: 0.35rem;
        }

        .rijks-card.rijks-card-has-notes {
            border-color: #ffb347;
            box-shadow: 0 0 0 1px #ffb347, 0 2px 10px rgba(0,0,0,0.6);
        }

        .rijks-card.rijks-card-no-notes { opacity: 0.95; }

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

        .rijks-card-caption {
            font-size: 0.9rem;
            color: #c7c7c7;
            margin-bottom: 0.35rem;
        }

        .rijks-summary-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background-color: #262626;
            color: #f5f5f5;
            font-size: 0.85rem;
            margin-top: 0.5rem;
            margin-bottom: 1rem;
        }
        .rijks-summary-pill strong { color: #ff9900; }

        .rijks-export-panel {
            background-color: #181818;
            border-radius: 12px;
            padding: 1rem 1.25rem 1.1rem 1.25rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 1px solid #262626;
            margin-top: 0.75rem;
            margin-bottom: 1.5rem;
        }

        .export-card {
            background-color: #202020;
            border-radius: 12px;
            padding: 0.8rem 0.9rem 0.95rem 0.9rem;
            border: 1px solid #333333;
            box-shadow: 0 2px 6px rgba(0,0,0,0.45);
            text-align: center;
        }

        .export-card h4 { margin: 0 0 0.4rem 0; font-size: 0.95rem; }
        .export-card p { font-size: 0.8rem; color: #c7c7c7; margin-bottom: 0.6rem; }

        .rijks-footer {
            margin-top: 2.5rem;
            padding-top: 0.75rem;
            border-top: 1px solid #262626;
            font-size: 0.8rem;
            color: #aaaaaa;
            text-align: center;
        }

        /* =========================================
           Gallery card micro-refinements
        ========================================= */

        .rijks-card-title {
            font-size: 0.95rem;
            line-height: 1.25;
            margin-top: 0.5rem;
            color: #f1f1f1;
        }

        .rijks-card-caption {
            font-size: 0.8rem;
            color: #b8b8b8;
            margin-bottom: 0.25rem;
        }

        .rijks-card:hover {
            background-color: rgba(255, 255, 255, 0.02);
        }

        /* Highlight for artworks marked as comparison candidates */
        .rijks-card-compare-candidate {
            border-color: #ffb347;
            box-shadow:
                0 0 0 1px #ffb347,
                0 4px 14px rgba(0, 0, 0, 0.9);
            position: relative;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def show_footer() -> None:
    """Show a small footer acknowledging the Rijksmuseum API."""
    st.markdown(
        """
        <div class="rijks-footer">
            Rijksmuseum Explorer — prototype created for study & research purposes.<br>
            Data & images provided by the Rijksmuseum API.
        </div>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()

# ============================================================
# PDF builder (illustrated)
# ============================================================
def build_pdf_buffer(favorites: dict, notes: dict) -> bytes | None:
    """
    Build an illustrated PDF (one artwork per page) using ReportLab.

    Returns a bytes buffer (ready to be sent to st.download_button) or None
    when ReportLab is not available or there are no favorites.
    """
    if not REPORTLAB_AVAILABLE or not favorites:
        return None

    pdf_meta = load_pdf_meta()
    include_cover = bool(pdf_meta.get("include_cover", True))
    include_opening_text = bool(pdf_meta.get("include_opening_text", True))
    include_notes_flag = bool(pdf_meta.get("include_notes", True))
    opening_text_cfg = (pdf_meta.get("opening_text") or "").strip()

    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    page_width, page_height = A4

    margin_left, margin_right = 50, 50
    margin_top = page_height - 80
    margin_bottom = 60

    def draw_footer():
        """Draw footer with title + generation timestamp on the current page."""
        c.setFont("Helvetica", 8)
        footer_left = f"Rijksmuseum Explorer — My selection ({len(favorites)} artworks)"
        generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")
        footer_right = f"Generated on {generated_on}"
        y_footer = margin_bottom
        c.drawString(margin_left, y_footer, footer_left)
        c.drawRightString(page_width - margin_right, y_footer, footer_right)

    def draw_text_block(title: str, text: str, y_start: float, cont_header: str) -> float:
        """
        Draw a titled text block, handling pagination for long content.

        Returns the new y position after the block.
        """
        text = (text or "").strip()
        if not text:
            return y_start

        # If there is not enough space, open a new page and draw a continuation header
        if y_start < margin_bottom + 40:
            draw_footer()
            c.showPage()
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin_left, margin_top, cont_header)
            y_start = margin_top - 30

        c.setFont("Helvetica-Oblique", 11)
        c.drawString(margin_left, y_start, title)

        y = y_start - 18
        c.setFont("Helvetica", 10)

        for line in wrap(text, width=90):
            if y < margin_bottom + 20:
                # New page when we run out of vertical space
                draw_footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 12)
                c.drawString(margin_left, margin_top, cont_header)
                y = margin_top - 30
                c.setFont("Helvetica", 10)
            c.drawString(margin_left, y, line)
            y -= 14

        return y

    total = len(favorites)

    # 1) Cover
    if include_cover:
        cover_title = "Rijksmuseum Explorer — My selection"
        generated_on = datetime.now().strftime("%Y-%m-%d %H:%M")

        c.setFont("Helvetica-Bold", 24)
        c.drawString(margin_left, page_height - 180, cover_title)

        c.setFont("Helvetica", 11)
        c.drawString(margin_left, page_height - 220, f"Generated on: {generated_on}")
        c.drawString(margin_left, page_height - 238, f"{total} artwork(s) in this selection")

        draw_footer()
        c.showPage()

    # 2) Opening text (optional introduction)
    if include_opening_text and opening_text_cfg:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin_left, margin_top, "Introduction")

        y = margin_top - 35
        c.setFont("Helvetica", 11)

        for line in wrap(opening_text_cfg, width=90):
            if y < margin_bottom + 20:
                draw_footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 16)
                c.drawString(margin_left, margin_top, "Introduction (cont.)")
                y = margin_top - 35
                c.setFont("Helvetica", 11)
            c.drawString(margin_left, y, line)
            y -= 15

        draw_footer()
        c.showPage()

    # 3) Contents page listing all artworks
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin_left, margin_top, "Contents")

    y = margin_top - 35
    c.setFont("Helvetica", 11)

    for idx, (obj_num, art) in enumerate(favorites.items(), start=1):
        title = art.get("title", "Untitled")
        maker = art.get("principalOrFirstMaker", "Unknown artist")
        line = f"{idx}. {title} — {maker} (ID: {obj_num})"

        for wrapped_line in wrap(line, width=90):
            if y < margin_bottom + 20:
                draw_footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 16)
                c.drawString(margin_left, margin_top, "Contents (cont.)")
                y = margin_top - 35
                c.setFont("Helvetica", 11)
            c.drawString(margin_left, y, wrapped_line)
            y -= 15

    draw_footer()
    c.showPage()

    # 4) One artwork per page
    for idx, (obj_num, art) in enumerate(favorites.items(), start=1):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin_left, margin_top, "Rijksmuseum Selection")
        c.setFont("Helvetica", 11)
        c.drawString(margin_left, margin_top - 24, f"Artwork {idx} of {total}")

        title = art.get("title", "Untitled")
        maker = art.get("principalOrFirstMaker", "Unknown artist")
        dating = art.get("dating", {}) or {}
        date = dating.get("presentingDate") or dating.get("year") or ""
        link = art.get("links", {}).get("web", "")
        img_url = get_best_image_url(art)

        thumb_w, thumb_h = 170, 170
        x_image = margin_left
        y_image_top = margin_top - 80
        x_text = x_image + thumb_w + 25
        y_text = y_image_top

        image_drawn = False

        # Thumbnail
        if img_url:
            try:
                resp = requests.get(img_url, timeout=8)
                resp.raise_for_status()
                image_data = io.BytesIO(resp.content)
                img_reader = ImageReader(image_data)

                iw, ih = img_reader.getSize()
                ratio = min(thumb_w / iw, thumb_h / ih)
                draw_w, draw_h = iw * ratio, ih * ratio

                c.drawImage(
                    img_reader,
                    x_image,
                    y_image_top - draw_h,
                    width=draw_w,
                    height=draw_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                image_drawn = True
            except Exception:
                # If the image fails, we simply continue with text only
                pass

        # Basic metadata block beside the image
        c.setFont("Helvetica-Bold", 14)
        c.drawString(x_text, y_text, title)

        c.setFont("Helvetica", 11)
        y_text -= 18
        c.drawString(x_text, y_text, f"Artist: {maker}")

        if date:
            y_text -= 14
            c.drawString(x_text, y_text, f"Date: {date}")

        y_text -= 14
        c.drawString(x_text, y_text, f"Object ID: {obj_num}")

        if link:
            y_text -= 14
            short_link = link.replace("https://", "")
            c.drawString(x_text, y_text, f"Link: {short_link}")
        # Text blocks: somente research notes (comentários específicos removidos)
        y_cursor = (y_image_top - thumb_h - 40) if image_drawn else (y_text - 28)
        y_cursor = min(y_cursor, y_text - 28)

        if include_notes_flag:
            note_text = notes.get(obj_num, "")
            note_text = note_text.strip() if isinstance(note_text, str) else ""
            y_cursor = draw_text_block(
                "Research notes:",
                note_text,
                y_cursor,
                f"Notes (cont.) — {obj_num}",
            )

            draw_footer()
        c.showPage()

    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ============================================================
# Page header & introductory text
# ============================================================
st.markdown("## ⭐ My selection")

st.write(
    "This page shows all artworks you have saved in your selection. "
    "Selections are stored locally in a small favorites file so they can be "
    "restored when you reopen or reload the app. "
    "From here you can refine your selection, manage research notes and export data."
)

st.caption(
    "Selections and research notes are stored locally on this device "
    "(favorites and notes files). "
    "If you want to start a completely fresh search with no pre-selected artworks, "
    "use **Clear my entire selection** below."
)

st.caption(
    "To compare artworks side by side, mark up to **4 artworks** here as "
    "comparison candidates and then open the **🖼️ Compare Artworks** page."
)

# ============================================================
# Load favorites & notes from local files
# ============================================================
if "favorites" not in st.session_state:
    if FAV_FILE.exists():
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                st.session_state["favorites"] = data if isinstance(data, dict) else {}
        except Exception:
            st.session_state["favorites"] = {}
    else:
        st.session_state["favorites"] = {}

favorites: dict = st.session_state["favorites"]

load_notes()
notes: dict = st.session_state.get("notes", {})

# Flag para avisar quando o limite de 4 candidatos é atingido
if "cmp_limit_warning" not in st.session_state:
    st.session_state["cmp_limit_warning"] = False

# Versão dos checkboxes de comparação (para forçar recriação quando necessário)
if "cmp_key_generation" not in st.session_state:
    st.session_state["cmp_key_generation"] = 0

# ------------------------------------------------------------
# NEW: auto-clean – keep at most 4 comparison candidates
# ------------------------------------------------------------
def get_compare_candidates_from_favorites(fav: dict) -> list[str]:
    """Return objectNumbers marked as comparison candidates inside favorites."""
    return [
        obj_num
        for obj_num, art in fav.items()
        if isinstance(art, dict) and art.get("_compare_candidate")
    ]

candidate_ids_all = get_compare_candidates_from_favorites(favorites)

if len(candidate_ids_all) > 4:
    # Keep only the first 4, remove the rest
    for obj_num in candidate_ids_all[4:]:
        art = favorites.get(obj_num)
        if isinstance(art, dict) and art.get("_compare_candidate"):
            art.pop("_compare_candidate", None)
            favorites[obj_num] = art

    st.session_state["favorites"] = favorites
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ============================================================
# Comparison candidates helper
# ============================================================
if "compare_candidates" not in st.session_state:
    # This will be kept in sync from favorites["_compare_candidate"] flags
    st.session_state["compare_candidates"] = []


def get_compare_candidates_from_favorites(fav: dict) -> list[str]:
    """
    Return a list of objectNumbers that are marked as comparison candidates
    in the favorites dictionary via the `_compare_candidate` flag.
    """
    return [
        obj_num
        for obj_num, art in fav.items()
        if isinstance(art, dict) and art.get("_compare_candidate")
    ]


# ------------------------------------------------------------
# One-time sidebar tip state
# ------------------------------------------------------------
if "sidebar_tip_dismissed" not in st.session_state:
    st.session_state["sidebar_tip_dismissed"] = False

if "sidebar_tip_version" not in st.session_state:
    st.session_state["sidebar_tip_version"] = 1


# ============================================================
# Analytics — page view (only once per session)
# ============================================================
if "analytics_my_selection_viewed" not in st.session_state:
    st.session_state["analytics_my_selection_viewed"] = True
    track_event(
        event="page_view",
        page="My_Selection",
        props={
            "has_favorites": bool(favorites),
            "favorites_count": len(favorites) if isinstance(favorites, dict) else 0,
        },
    )


# ============================================================
# Empty selection guard
# ============================================================
if not favorites:
    st.info(
        "You currently have no artworks in your selection. "
        "Go to the **Rijksmuseum Explorer** page and mark "
        "**In my selection** on any artwork you want to keep."
    )
    show_footer()
    st.stop()


# ============================================================
# Selection statistics summary
# ============================================================
stats = compute_selection_stats(favorites)

noted_ids = [
    obj_num
    for obj_num, text in notes.items()
    if isinstance(text, str) and text.strip() and obj_num in favorites
]
num_noted = len(noted_ids)

st.markdown(
    f'<div class="rijks-summary-pill">'
    f'You have <strong>{stats["count"]}</strong> artwork(s) in your selection.'
    f"</div>",
    unsafe_allow_html=True,
)

with st.expander("📊 Selection insights", expanded=True):
    st.write(f"- **Number of artworks:** {stats['count']}")
    st.write(f"- **Distinct artists:** {stats['artists']}")
    st.write(f"- **Artworks with research notes:** {num_noted}")

    if stats["min_year"] and stats["max_year"]:
        if stats["min_year"] == stats["max_year"]:
            st.write(f"- **Approximate date:** around **{stats['min_year']}**")
        else:
            st.write(
                f"- **Approximate date range:** "
                f"from **{stats['min_year']}** to **{stats['max_year']}**"
            )
    else:
        st.write("- **Date range:** not available from API metadata.")


# ============================================================
# Sidebar controls (filters, sorting, gallery options)
# ============================================================
default_min_year = stats["min_year"] if stats["min_year"] is not None else 1400
default_max_year = stats["max_year"] if stats["max_year"] is not None else 2025

with st.sidebar:
    st.markdown("## 🔧 My Selection Controls")

    # One-time sidebar collapse hint
    if not st.session_state.get("sidebar_tip_dismissed", False):
        with st.container():
            st.info(
                "💡 Tip: You can collapse this panel using the « icon on the top left.",
                icon="ℹ️",
            )
            if st.button("Got it", key="dismiss_sidebar_tip"):
                st.session_state["sidebar_tip_dismissed"] = True
                st.rerun()

    # Internal metadata filters
    with st.expander("🔍 Filter within selection", expanded=False):
        text_filter = st.text_input(
            "Search in title, artist, materials, techniques or places",
            value="",
            key="sb_text_filter",
        )

        year_min, year_max = st.slider(
            "Approximate year range",
            min_value=1400,
            max_value=2025,
            value=(default_min_year, default_max_year),
            step=10,
            key="sb_year_range",
        )

        artist_filter = st.text_input(
            "Artist contains",
            value="",
            key="sb_artist_filter",
        )

        object_type_filter = st.text_input(
            "Object type contains",
            value="",
            key="sb_object_type_filter",
        )

    # Notes-level filter (with / without notes)
    total_artworks = stats["count"]
    total_with_notes = num_noted
    total_without_notes = total_artworks - total_with_notes

    options_labels = [
        f"All artworks ({total_artworks})",
        f"Only artworks with notes ({total_with_notes})",
        f"Only artworks without notes ({total_without_notes})",
    ]

    selection_filter_label = st.radio(
        "Show in gallery:",
        options=options_labels,
        index=0,
        key="selection_filter_radio",
    )

    # Notes keyword filter
    note_filter = st.text_input(
        "Notes keyword filter (optional)",
        value="",
        key="note_filter",
    )
    note_filter_lower = note_filter.strip().lower()

    # Gallery display controls
    st.markdown("### 🧭 Gallery")

    sort_label = st.selectbox(
        "Order artworks by",
        options=[
            "Default (as saved)",
            "Artist (A–Z)",
            "Title (A–Z)",
            "Year (oldest → newest)",
            "Year (newest → oldest)",
            "Notes first",
        ],
        index=0,
        key="sb_sort_label",
    )

    gallery_view = st.selectbox(
        "Gallery view mode",
        options=["Grid (default)", "Group by artist"],
        index=0,
        key="sb_gallery_view",
    )

    show_images = st.toggle(
        "Show thumbnails",
        value=True,
        key="show_images_toggle",
    )

    compact_mode = st.toggle(
        "Compact gallery mode",
        value=False,
        key="compact_mode_toggle",
    )


# ============================================================
# Derived flags from sidebar state
# ============================================================
if selection_filter_label.startswith("All artworks"):
    selection_filter_code = "all"
elif "with notes" in selection_filter_label:
    selection_filter_code = "with_notes"
else:
    selection_filter_code = "without_notes"

# True when the user picks "Group by artist" in the sidebar
group_by_artist = (gallery_view == "Group by artist")

# Default: no comparison checkboxes in grouped view
# (we will override this when group_by_artist is True)
enable_compare_grouped = False

cards_per_row = 5 if compact_mode else 3

filters_active = any(
    [
        text_filter.strip(),
        artist_filter.strip(),
        object_type_filter.strip(),
        (year_min, year_max) != (1400, 2025),
    ]
)


# ============================================================
# Apply internal metadata filters to favorites
# ============================================================
filtered_favorites: dict = favorites
if filters_active:
    filtered_favorites = {
        obj_num: art
        for obj_num, art in favorites.items()
        if passes_selection_filters(
            art=art,
            text_filter=text_filter,
            year_min=year_min,
            year_max=year_max,
            artist_filter=artist_filter,
            object_type_filter=object_type_filter,
        )
    }
    st.caption(
        f"Showing {len(filtered_favorites)} of {len(favorites)} artworks "
        f"after internal metadata filters."
    )
else:
    st.caption("No internal metadata filter applied (showing all artworks in your selection).")


# ============================================================
# Export panel (CSV / JSON / PDF / share code / notes exports)
# ============================================================
st.markdown('<div class="rijks-export-panel">', unsafe_allow_html=True)
st.markdown("### Export & share selection")

# Build base CSV with artworks in the selection
rows: list[list[str]] = []
for obj_num, art in favorites.items():
    title = art.get("title", "")
    maker = art.get("principalOrFirstMaker", "")
    dating = art.get("dating", {}) or {}
    date = dating.get("presentingDate") or dating.get("year") or ""
    link = art.get("links", {}).get("web", "")

    # NEW: flag indicando se esta obra tem nota de pesquisa
    note_text = notes.get(obj_num, "")
    has_note = isinstance(note_text, str) and note_text.strip() != ""

    rows.append([obj_num, title, maker, date, link, has_note])

csv_data = None
if rows:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["objectNumber", "title", "artist", "date", "web_link", "has_notes"]
    )
    writer.writerows(rows)
    csv_data = buffer.getvalue()

# Full favorites JSON (pretty + compact)
favorites_json_pretty = json.dumps(favorites, ensure_ascii=False, indent=2)
favorites_json_compact = json.dumps(favorites, ensure_ascii=False)

# Collection code (base64 of compact JSON)
collection_code = base64.b64encode(
    favorites_json_compact.encode("utf-8")
).decode("ascii")

# Notes exports (CSV + JSON)
notes_rows: list[list[str]] = []
for obj_num, art in favorites.items():
    note_text = notes.get(obj_num, "")
    note_text = note_text.strip() if isinstance(note_text, str) else ""
    if not note_text:
        continue

    title = art.get("title", "")
    maker = art.get("principalOrFirstMaker", "")
    notes_rows.append([obj_num, title, maker, note_text])

notes_csv_data = None
if notes_rows:
    notes_buffer = io.StringIO()
    notes_writer = csv.writer(notes_buffer)
    notes_writer.writerow(["objectNumber", "title", "artist", "note"])
    notes_writer.writerows(notes_rows)
    notes_csv_data = notes_buffer.getvalue()

notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

col1, col2, col3, col4 = st.columns(4)

# ----- CSV export -----
with col1:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>CSV</h4>", unsafe_allow_html=True)
    st.markdown("<p>Table format for Excel/Sheets.</p>", unsafe_allow_html=True)
    if csv_data:
        clicked = st.download_button(
            "📄 Download CSV",
            csv_data,
            "rijks_selection.csv",
            "text/csv",
            key="dl_selection_csv",
        )
        if clicked:
            track_event(
                event="export_download",
                page="My_Selection",
                props={"format": "csv", "scope": "selection", "count": len(favorites)},
            )
    else:
        st.caption("No data.")
    st.markdown("</div>", unsafe_allow_html=True)

# ----- JSON export -----
with col2:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>JSON</h4>", unsafe_allow_html=True)
    st.markdown("<p>For scripts, apps and APIs.</p>", unsafe_allow_html=True)
    clicked = st.download_button(
        "🧾 Download JSON",
        favorites_json_pretty,
        "rijks_selection.json",
        "application/json",
        key="dl_selection_json",
    )
    if clicked:
        track_event(
            event="export_download",
            page="My_Selection",
            props={"format": "json", "scope": "selection", "count": len(favorites)},
        )
    st.markdown("</div>", unsafe_allow_html=True)

# ----- PDF export -----
with col3:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>PDF</h4>", unsafe_allow_html=True)
    st.markdown("<p>Printable report of your selection.</p>", unsafe_allow_html=True)

    # NEW: escolher o escopo do PDF
    pdf_scope = st.radio(
        "Include in PDF:",
        options=[
            "All artworks in my selection",
            "Only artworks with notes",
        ],
        index=0,
        key="pdf_scope_radio",
    )

    if "pdf_buffer" not in st.session_state:
        st.session_state["pdf_buffer"] = None

    if st.button("Prepare PDF", key="prepare_pdf_btn"):
        # Decide quais obras entram no PDF de acordo com o escopo
        if pdf_scope == "Only artworks with notes":
            favorites_for_pdf = {
                obj_num: art
                for obj_num, art in favorites.items()
                if isinstance(notes.get(obj_num, ""), str)
                and notes.get(obj_num, "").strip() != ""
            }
        else:
            favorites_for_pdf = favorites

        track_event(
            event="export_prepare",
            page="My_Selection",
            props={
                "format": "pdf",
                "scope": "selection",
                "count": len(favorites_for_pdf),
                "pdf_scope": pdf_scope,
            },
        )

        if not REPORTLAB_AVAILABLE:
            st.warning("Install `reportlab` to enable PDF export.")
        else:
            if not favorites_for_pdf:
                st.warning(
                    "No artworks match the chosen PDF scope. "
                    "Add notes to at least one artwork or change the scope."
                )
                st.session_state["pdf_buffer"] = None
            else:
                with st.spinner("Preparing PDF with thumbnails..."):
                    buf = build_pdf_buffer(favorites_for_pdf, notes)
                if buf:
                    st.session_state["pdf_buffer"] = buf
                    st.success(
                        f"PDF ready! ({len(favorites_for_pdf)} artwork(s) included)"
                    )
                else:
                    st.warning("PDF could not be generated.")

    if st.session_state["pdf_buffer"]:
        clicked = st.download_button(
            "📑 Download PDF",
            st.session_state["pdf_buffer"],
            "rijks_selection.pdf",
            "application/pdf",
            key="dl_selection_pdf",
        )
        if clicked:
            track_event(
                event="export_download",
                page="My_Selection",
                props={
                    "format": "pdf",
                    "scope": "selection",
                    "count": len(favorites),
                },
            )
        if clicked:
            track_event(
                event="export_download",
                page="My_Selection",
                props={"format": "pdf", "scope": "selection", "count": len(favorites)},
            )

    st.markdown("</div>", unsafe_allow_html=True)

# ----- Share code + notes exports -----
with col4:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>Share & notes</h4>", unsafe_allow_html=True)
    st.markdown(
        "<p>Share your selection and export research notes.</p>",
        unsafe_allow_html=True,
    )

    # Selection sharing via base64 code
    with st.expander("🔗 Share selection code", expanded=False):
        st.caption("Copy this code to share your selection with another user:")
        st.code(collection_code, language=None)

        import_code = st.text_area(
            "Collection code to import",
            value="",
            height=80,
            key="import_code",
        )

        if st.button("Load selection from code"):
            if not import_code.strip():
                st.warning("Please paste a collection code first.")
            else:
                try:
                    decoded = base64.b64decode(import_code.encode("ascii")).decode(
                        "utf-8"
                    )
                    data = json.loads(decoded)
                    if isinstance(data, dict):
                        st.session_state["favorites"] = data
                        try:
                            with open(FAV_FILE, "w", encoding="utf-8") as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                        st.success("Selection loaded successfully from code.")
                        st.rerun()
                    else:
                        st.error("The code is valid text but not in the expected format.")
                except Exception as e:
                    st.error(f"Could not decode the collection code: {e}")

    # Notes exports
    with st.expander("📝 Export research notes", expanded=False):
        st.caption(
            "Download your research notes for use in Excel/Sheets or in other tools."
        )

        if notes_csv_data:
            clicked = st.download_button(
                "📄 Download notes (CSV)",
                notes_csv_data,
                "rijks_notes.csv",
                "text/csv",
                key="dl_notes_csv",
            )
            if clicked:
                track_event(
                    event="export_download",
                    page="My_Selection",
                    props={
                        "format": "csv",
                        "scope": "notes",
                        "count": len(notes_rows),
                    },
                )
        else:
            st.caption("No notes available yet.")

        clicked = st.download_button(
            "🧾 Download notes (JSON)",
            notes_json,
            "rijks_notes.json",
            "application/json",
            key="dl_notes_json",
        )
        if clicked:
            track_event(
                event="export_download",
                page="My_Selection",
                props={
                    "format": "json",
                    "scope": "notes",
                    "count": len(notes_rows),
                },
            )

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Clear entire selection (local favorites file + session)
# ============================================================
if st.button("Clear my entire selection"):
    # Clear in-memory favorites
    st.session_state["favorites"] = {}
    favorites = {}

    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # When clearing everything, also reset comparison checkbox key generation
    st.session_state["cmp_key_generation"] = st.session_state.get(
        "cmp_key_generation", 0
    ) + 1

    st.session_state["detail_art_id"] = None
    st.session_state["compare_candidates"] = []

    # Also clear any prepared PDF buffer (it may refer to the old selection)
    st.session_state["pdf_buffer"] = None

    st.success("Your selection has been cleared.")
    st.rerun()


# ============================================================
# Gallery + comparison logic helpers
# ============================================================
def get_year_for_sort(art: dict):
    """Return a numeric year for sorting (when available) to support year-based ordering."""
    dating = art.get("dating") or {}
    y = dating.get("year")
    if isinstance(y, int):
        return y
    pd = dating.get("presentingDate")
    if isinstance(pd, str) and len(pd) >= 4 and pd[:4].isdigit():
        try:
            return int(pd[:4])
        except Exception:
            return None
    return None


def has_note_text(obj_num: str) -> bool:
    """Return True if the artwork has a non-empty research note."""
    txt = notes.get(obj_num, "")
    return isinstance(txt, str) and txt.strip() != ""


def has_note(obj_id: str) -> bool:
    """Alias for has_note_text (kept for clarity in filters)."""
    txt = notes.get(obj_id, "")
    return isinstance(txt, str) and txt.strip() != ""


# ------------------------------------------------------------
# Base items = favorites after metadata filters
# ------------------------------------------------------------
base_items: list[tuple[str, dict]] = list(filtered_favorites.items())

# -----------------------------
# Global sorting over base_items
# -----------------------------
if sort_label == "Artist (A–Z)":
    base_items.sort(
        key=lambda item: (
            item[1].get("principalOrFirstMaker", ""),
            item[1].get("title", ""),
        )
    )
elif sort_label == "Title (A–Z)":
    base_items.sort(
        key=lambda item: (
            item[1].get("title", ""),
            item[1].get("principalOrFirstMaker", ""),
        )
    )
elif sort_label == "Year (oldest → newest)":
    base_items.sort(
        key=lambda item: (
            get_year_for_sort(item[1]) is None,
            get_year_for_sort(item[1]) or 10**9,
        )
    )
elif sort_label == "Year (newest → oldest)":
    base_items.sort(
        key=lambda item: (
            get_year_for_sort(item[1]) is None,
            -(get_year_for_sort(item[1]) or -10**9),
        )
    )
elif sort_label == "Notes first":
    base_items.sort(
        key=lambda item: (
            not has_note_text(item[0]),
            item[1].get("principalOrFirstMaker", ""),
            item[1].get("title", ""),
        )
    )

# -----------------------------
# Filter by keyword inside notes
# -----------------------------
if note_filter_lower:
    base_items = [
        (obj_num, art)
        for obj_num, art in base_items
        if note_filter_lower in (notes.get(obj_num, "") or "").lower()
    ]

# -----------------------------
# High-level filter: with / without notes
# -----------------------------
if selection_filter_code == "with_notes":
    base_items = [(obj_num, art) for obj_num, art in base_items if has_note(obj_num)]
elif selection_filter_code == "without_notes":
    base_items = [
        (obj_num, art) for obj_num, art in base_items if not has_note(obj_num)
    ]

# ------------------------------------------------------------
# Summary after all filters (metadata + notes)
# ------------------------------------------------------------
total_after_filters = len(base_items)
artists_after_filters = len(
    {
        (art.get("principalOrFirstMaker") or "Unknown artist")
        for _, art in base_items
    }
)

st.caption(
    f"Current view: **{total_after_filters}** artwork(s) "
    f"from **{artists_after_filters}** artist(s) after all filters."
)

# -----------------------------
# Empty result after filters
# -----------------------------
if not base_items:
    st.info(
        "No artworks match the current filters "
        "(metadata filters, notes keyword and notes status)."
    )

else:
    # ---------------------------------------------------------
    # Human-readable summary of active filters
    # ---------------------------------------------------------
    filters_summary: list[str] = []

    if filters_active:
        if text_filter.strip():
            filters_summary.append(f"text contains '{text_filter.strip()}'")
        if (year_min, year_max) != (1400, 2025):
            filters_summary.append(f"year between {year_min}-{year_max}")
        if artist_filter.strip():
            filters_summary.append(f"artist contains '{artist_filter.strip()}'")
        if object_type_filter.strip():
            filters_summary.append(
                f"object type contains '{object_type_filter.strip()}'"
            )

    if selection_filter_code == "with_notes":
        filters_summary.append("only artworks with notes")
    elif selection_filter_code == "without_notes":
        filters_summary.append("only artworks without notes")

    if note_filter_lower:
        filters_summary.append(f"notes contain '{note_filter}'")

    filters_summary.append(
        "view: group by artist" if group_by_artist else "view: grid"
    )

    if filters_summary:
        st.caption("Active filters: " + " · ".join(filters_summary))
    else:
        st.caption("Active filters: none (full selection).")

    # --------------------------------------------------------
    # Cross-page comparison candidates: summary, filter & clear
    # --------------------------------------------------------
    # Canonical list of comparison candidates derived from favorites flags
    candidate_ids = get_compare_candidates_from_favorites(favorites)
    st.session_state["compare_candidates"] = candidate_ids

    show_only_cmp = False

    if candidate_ids:
        with st.expander(
                "🎯 Comparison candidates (from My Selection)", expanded=False
        ):
            st.write(
                "These artworks are marked for cross-page comparison. "
                "You can focus the gallery on them or clear all marks at once."
            )

            # Human-readable list of marked artworks
            for obj_num in candidate_ids:
                art = favorites.get(obj_num, {})
                title = art.get("title", "Untitled")
                maker = art.get("principalOrFirstMaker", "Unknown artist")
                st.markdown(
                    f"- **{title}** — *{maker}*  \n`{obj_num}`"
                )

            # Option: show only comparison candidates in the gallery
            show_only_cmp = st.checkbox(
                "Show only these artworks in the gallery below",
                key="show_only_cmp_checkbox",
            )

            # Button: clear all comparison marks at once
            if st.button("Clear all comparison marks", key="clear_all_cmp"):
                # Remove the `_compare_candidate` flag from each favorite
                for obj_num in candidate_ids:
                    art = favorites.get(obj_num)
                    if isinstance(art, dict):
                        art.pop("_compare_candidate", None)
                        favorites[obj_num] = art

                # Persist updated favorites to disk
                st.session_state["favorites"] = favorites
                try:
                    with open(FAV_FILE, "w", encoding="utf-8") as f:
                        json.dump(favorites, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                # Clear in-memory list of comparison candidates
                st.session_state["compare_candidates"] = []

                # Força recriação dos checkboxes com novas keys
                st.session_state["cmp_key_generation"] = (
                        st.session_state.get("cmp_key_generation", 0) + 1
                )

                st.success("All comparison marks have been cleared.")
                st.rerun()
    else:
        st.caption(
            "No artworks are currently marked for cross-page comparison."
        )

    # If the user wants to focus only on comparison candidates,
    # restrict the base_items list accordingly
    if show_only_cmp and candidate_ids:
        base_items = [
            (obj_num, art)
            for obj_num, art in base_items
            if obj_num in candidate_ids
        ]

        total_after_filters = len(base_items)
        st.caption(
            f"Gallery restricted to **{total_after_filters}** "
            f"comparison candidate(s)."
        )


    # =========================================================
    # Card rendering helper (used by both gallery modes)
    # =========================================================
    def handle_compare_logic(obj_num: str, desired: bool):
        """
        Atualiza o status de comparação de um artwork.

        - Garante no máximo 4 candidatos.
        - Atualiza favorites[obj_num]['_compare_candidate'].
        - Persiste em disco.
        - Quando o usuário tenta marcar o 5º, dispara um aviso,
          incrementa cmp_key_generation e dá st.rerun()
          para recriar os checkboxes com o estado correto.
        """
        art = favorites.get(obj_num)
        if not isinstance(art, dict):
            return

        is_candidate = bool(art.get("_compare_candidate"))
        current_candidates = get_compare_candidates_from_favorites(favorites)

        # Usuário está tentando MARCAR como candidato
        if desired and not is_candidate:
            if len(current_candidates) >= 4:
                # Apenas avisa; não marca o 5º, recria checkboxes e rerun
                st.session_state["cmp_limit_warning"] = True
                st.session_state["cmp_key_generation"] = (
                        st.session_state.get("cmp_key_generation", 0) + 1
                )
                st.rerun()
                return
            art["_compare_candidate"] = True

        # Usuário está tentando DESMARCAR algo que já era candidato
        elif not desired and is_candidate:
            art.pop("_compare_candidate", None)

        else:
            # Nada mudou de fato
            return

        # Atualiza favorites em memória e em disco
        favorites[obj_num] = art
        st.session_state["favorites"] = favorites
        try:
            with open(FAV_FILE, "w", encoding="utf-8") as f:
                json.dump(favorites, f, ensure_ascii=False, indent=2)
        except Exception:
            # nunca quebrar a UI por erro de disco
            pass


    def render_cards(items: list[tuple[str, dict]], allow_compare: bool):
        """
        Render a grid of artwork cards.

        Parameters
        ----------
        items:
            List of (objectNumber, art_dict) tuples to render as cards.
        allow_compare:
            If True, show comparison checkboxes that mark artworks
            as comparison candidates (used across pages).
        """
        for start_idx in range(0, len(items), cards_per_row):
            row_items = items[start_idx: start_idx + cards_per_row]
            cols = st.columns(len(row_items))

            for col, (obj_num, art) in zip(cols, row_items):
                with col:
                    note_for_this = notes.get(obj_num, "")
                    has_notes_flag = isinstance(note_for_this, str) and note_for_this.strip()

                    # Base card classes
                    card_classes = "rijks-card"
                    card_classes += (
                        " rijks-card-has-notes"
                        if has_notes_flag
                        else " rijks-card-no-notes"
                    )

                    # Extra highlight quando é candidato à comparação
                    if isinstance(art, dict) and art.get("_compare_candidate"):
                        card_classes += " rijks-card-compare-candidate"
                    st.markdown(
                        f'<div class="{card_classes}">', unsafe_allow_html=True
                    )

                    img_url = cached_best_image_url(art)

                    # Thumbnail area
                    if show_images:
                        if img_url:
                            try:
                                st.image(img_url, use_container_width=True)
                            except Exception:
                                st.write("Error displaying image.")
                        else:
                            st.write("No valid image available via API.")
                    else:
                        st.caption("Thumbnails hidden for faster browsing.")

                    # Basic metadata
                    title = art.get("title", "Untitled")
                    maker = art.get("principalOrFirstMaker", "Unknown artist")

                    if compact_mode and isinstance(title, str) and len(title) > 60:
                        title = title[:57] + "..."

                    web_link = art.get("links", {}).get("web")
                    dating = art.get("dating", {}) or {}
                    presenting_date = dating.get("presentingDate")
                    year = dating.get("year")

                    st.markdown(
                        f'<div class="rijks-card-title">{title}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f'<div class="rijks-card-caption">{maker}</div>',
                        unsafe_allow_html=True,
                    )

                    if has_notes_flag:
                        st.caption("📝 Notes available for this artwork")

                    if presenting_date:
                        st.text(f"Date: {presenting_date}")
                    elif year:
                        st.text(f"Year: {year}")

                    st.text(f"Object ID: {obj_num}")

                    if web_link:
                        st.markdown(f"[View on Rijksmuseum website]({web_link})")

                    # Extra metadata (inside expander)
                    with st.expander("More details"):
                        long_title = art.get("longTitle")
                        object_types = art.get("objectTypes")
                        materials = art.get("materials")
                        techniques = art.get("techniques")
                        production_places = art.get("productionPlaces")

                        if long_title and long_title != title:
                            st.write(f"**Long title:** {long_title}")
                        if object_types:
                            st.write(f"**Object type(s):** {', '.join(object_types)}")
                        if materials:
                            st.write(f"**Materials:** {', '.join(materials)}")
                        if techniques:
                            st.write(f"**Techniques:** {', '.join(techniques)}")
                        if production_places:
                            st.write(
                                f"**Production place(s): {', '.join(production_places)}"
                            )

                    # --------------------------------------------------------
                    # Checkbox "Mark for comparison"
                    # --------------------------------------------------------
                    if allow_compare and obj_num:
                        is_candidate = bool(art.get("_compare_candidate"))

                        # Usa geração para forçar recriação quando necessário
                        cmp_gen = st.session_state.get("cmp_key_generation", 0)
                        cmp_key = f"cmp_candidate_{obj_num}_{cmp_gen}"
                        label = "Mark for comparison"

                        checked = st.checkbox(
                            label,
                            key=cmp_key,
                            value=is_candidate,
                        )

                        # Se o usuário mudou o estado do checkbox, aplica a lógica
                        if checked != is_candidate:
                            handle_compare_logic(obj_num, checked)

                    # Detail view button
                    if st.button("View details", key=f"detail_btn_{obj_num}"):
                        st.session_state["detail_art_id"] = obj_num

                    # Remove from selection (card level)
                    if st.button(
                            "Remove from my selection", key=f"remove_card_{obj_num}"
                    ):

                        track_event(
                            event="selection_remove_item",
                            page="My_Selection",
                            props={
                                "object_id": obj_num,
                                "artist": art.get("principalOrFirstMaker"),
                                "had_notes": bool(
                                    (
                                        st.session_state.get("notes", {})
                                        .get(obj_num, "")
                                        .strip()
                                    )
                                ),
                                "prev_count": len(favorites),
                                "origin": "card",
                            },
                        )

                        # Remove this artwork from favorites
                        favorites.pop(obj_num, None)
                        st.session_state["favorites"] = favorites

                        try:
                            with open(FAV_FILE, "w", encoding="utf-8") as f:
                                json.dump(favorites, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass

                        # If this artwork was open in detail view, close it
                        if st.session_state.get("detail_art_id") == obj_num:
                            st.session_state["detail_art_id"] = None

                        # Remove notes for this artwork as well
                        if "notes" in st.session_state:
                            st.session_state["notes"].pop(obj_num, None)
                            try:
                                with open(NOTES_FILE, "w", encoding="utf-8") as f:
                                    json.dump(
                                        st.session_state["notes"],
                                        f,
                                        ensure_ascii=False,
                                        indent=2,
                                    )
                            except Exception:
                                pass

                        st.success("Artwork removed from your selection.")
                        st.rerun()

                    st.markdown("</div>", unsafe_allow_html=True)


    # =========================================================
    # MODE A) GROUP BY ARTIST
    # =========================================================
    # Safety: default value in case something fails before the toggle is evaluated
    enable_compare_grouped = False

    if group_by_artist:
        st.markdown("### 👤 Artists overview")

        artists_per_page = st.select_slider(
            "Artists per page",
            options=[3, 5, 8, 12, 20],
            value=5,
        )

        sort_within_artist = st.selectbox(
            "Order artworks within each artist",
            options=[
                "Default (as saved)",
                "Title (A–Z)",
                "Year (oldest → newest)",
                "Year (newest → oldest)",
                "Notes first",
            ],
            index=0,
        )

        expand_artists = st.toggle(
            "Expand artist groups",
            value=False,
            help="Turn on to open all artist blocks by default.",
        )

        enable_compare_grouped = st.toggle(
            "Enable comparison in grouped view",
            value=False,
            help="Allow selecting artworks for comparison inside artist groups.",
            key="enable_compare_grouped_toggle",
        )

        # Group artworks by artist
        grouped: dict[str, list[tuple[str, dict]]] = {}
        for obj_num, art in base_items:
            artist = art.get("principalOrFirstMaker") or "Unknown artist"
            grouped.setdefault(artist, []).append((obj_num, art))

        artist_names = sorted(grouped.keys(), key=lambda x: x.lower())

        total_artists = len(artist_names)
        max_pages = max(1, (total_artists + artists_per_page - 1) // artists_per_page)

        page = st.number_input(
            "Artist page",
            min_value=1,
            max_value=max_pages,
            value=1,
            step=1,
        )

        start_a = (page - 1) * artists_per_page
        end_a = start_a + artists_per_page
        page_artists = artist_names[start_a:end_a]

        st.caption(
            f"Showing artist page {page} of {max_pages} — "
            f"{total_artists} artist(s) and {len(base_items)} artwork(s) total after filters."
        )


        def sort_items_for_artist(items: list[tuple[str, dict]]):
            """Apply the selected within-artist sorting option to a list of items."""
            if sort_within_artist == "Title (A–Z)":
                items.sort(
                    key=lambda it: (
                        it[1].get("title", ""),
                        it[1].get("principalOrFirstMaker", ""),
                    )
                )
            elif sort_within_artist == "Year (oldest → newest)":
                items.sort(
                    key=lambda it: (
                        get_year_for_sort(it[1]) is None,
                        get_year_for_sort(it[1]) or 10 ** 9,
                    )
                )
            elif sort_within_artist == "Year (newest → oldest)":
                items.sort(
                    key=lambda it: (
                        get_year_for_sort(it[1]) is None,
                        -(get_year_for_sort(it[1]) or -10 ** 9),
                    )
                )
            elif sort_within_artist == "Notes first":
                items.sort(
                    key=lambda it: (
                        not has_note_text(it[0]),
                        it[1].get("title", ""),
                    )
                )


        visible_items: list[tuple[str, dict]] = []

        # Render groups for the current page of artists
        for artist in page_artists:
            items = grouped.get(artist, [])
            sort_items_for_artist(items)
            visible_items.extend(items)

            years = [get_year_for_sort(a) for _, a in items]
            years = [y for y in years if isinstance(y, int)]
            min_y = min(years) if years else None
            max_y = max(years) if years else None
            notes_count = sum(1 for obj_id, _ in items if has_note_text(obj_id))

            subtitle_parts = [
                f"{len(items)} artwork(s)",
                f"{notes_count} with notes",
            ]
            if min_y and max_y:
                subtitle_parts.append(f"{min_y}–{max_y}")

            header_line = " • ".join(subtitle_parts)

            with st.expander(
                    f"👤 {artist} — {header_line}", expanded=expand_artists
            ):
                render_cards(items, allow_compare=enable_compare_grouped)

    # =========================================================
    # MODE B) GRID (default gallery)
    # =========================================================
    else:
        items_per_page = st.select_slider(
            "Artworks per page",
            options=[6, 9, 12, 18, 24, 36],
            value=12,
        )

        total_items = len(base_items)
        max_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        page = st.number_input(
            "Page",
            min_value=1,
            max_value=max_pages,
            value=1,
            step=1,
        )

        start_i = (page - 1) * items_per_page
        end_i = start_i + items_per_page
        page_items = base_items[start_i:end_i]

        st.caption(
            f"Showing page {page} of {max_pages} — "
            f"{total_items} artwork(s) total after filters."
        )

        st.markdown("### Mark artworks from your selection as comparison candidates")
        render_cards(page_items, allow_compare=True)

        # Aviso quando tentar marcar mais de 4
        if st.session_state.get("cmp_limit_warning"):
            st.warning(
                "You can mark at most 4 artworks for comparison. "
                "Unmark another one first."
            )
            st.session_state["cmp_limit_warning"] = False

        # Recompute candidates from favorites (single source of truth) and
        # store them in session_state for the Compare Artworks page
        compare_candidates = get_compare_candidates_from_favorites(favorites)
        st.session_state["compare_candidates"] = compare_candidates
        num_candidates = len(compare_candidates)
        if num_candidates == 0:
            st.info(
                "Mark artworks above with **Mark for comparison** to prepare "
                "a side-by-side comparison on the **Compare Artworks** page."
            )
        else:
            st.success(
                f"Currently marked for comparison: **{num_candidates}** artwork(s). "
                "Open the **Compare Artworks** page to run the side-by-side view."
            )
# ============================================================
# Detail view + research notes editor
# ============================================================
detail_id = st.session_state.get("detail_art_id")
if detail_id and detail_id in favorites:
    art = favorites[detail_id]

    # Analytics: only log the first time a given artwork is opened in detail view
    analytics_key = f"analytics_detail_opened_{detail_id}"
    if analytics_key not in st.session_state:
        st.session_state[analytics_key] = True

        dating = art.get("dating") or {}
        year = dating.get("year") or dating.get("presentingDate")
        title = art.get("title")

        track_event(
            event="artwork_detail_opened",
            page="My_Selection",
            props={
                "object_id": detail_id,
                "artist": art.get("principalOrFirstMaker"),
                "title": title,
                "year": year,
                "has_notes": bool(
                    isinstance(
                        st.session_state.get("notes", {}).get(detail_id), str
                    )
                    and st.session_state["notes"][detail_id].strip()
                ),
            },
        )

    st.markdown("---")
    st.subheader("🔍 Detail view")

    img_url = get_best_image_url(art)
    title = art.get("title", "Untitled")
    maker = art.get("principalOrFirstMaker", "Unknown artist")
    web_link = art.get("links", {}).get("web")
    dating = art.get("dating", {}) or {}
    presenting_date = dating.get("presentingDate")
    year = dating.get("year")

    col_img, col_meta = st.columns([3, 2])

    with col_img:
        if img_url:
            zoom = st.slider(
                "Zoom (relative size)",
                min_value=50,
                max_value=200,
                value=120,
                step=10,
                key=f"zoom_{detail_id}",
            )
            base_width = 600
            width = int(base_width * zoom / 100)
            st.image(img_url, width=width)
        else:
            st.write("No valid image available via API.")

    with col_meta:
        st.write(f"**Title:** {title}")
        st.write(f"**Artist:** {maker}")
        st.write(f"**Object ID:** {detail_id}")
        if presenting_date:
            st.write(f"**Date:** {presenting_date}")
        elif year:
            st.write(f"**Year:** {year}")

        long_title = art.get("longTitle")
        object_types = art.get("objectTypes")
        materials = art.get("materials")
        techniques = art.get("techniques")
        production_places = art.get("productionPlaces")

        if long_title and long_title != title:
            st.write(f"**Long title:** {long_title}")
        if object_types:
            st.write(f"**Object type(s):** {', '.join(object_types)}")
        if materials:
            st.write(f"**Materials:** {', '.join(materials)}")
        if techniques:
            st.write(f"**Techniques:** {', '.join(techniques)}")
        if production_places:
            st.write(f"**Production place(s): {', '.join(production_places)}")

        if web_link:
            st.markdown(f"[Open on Rijksmuseum website for full zoom]({web_link})")

    st.markdown("### 📝 Research notes")

    existing_note = st.session_state["notes"].get(detail_id, "")
    note_text = st.text_area(
        "Write your notes for this artwork:",
        value=existing_note,
        height=160,
        key=f"note_{detail_id}",
    )

    # Save notes + analytics
    if st.button("Save notes", key=f"save_note_{detail_id}"):
        st.session_state["notes"][detail_id] = note_text
        save_notes()
        st.success("Notes saved successfully.")

        track_event(
            event="note_saved",
            page="My_Selection",
            props={
                "object_id": detail_id,
                "note_len": len(note_text.strip())
                if isinstance(note_text, str)
                else 0,
                "has_note": bool(isinstance(note_text, str) and note_text.strip()),
            },
        )

    # Remove from selection (detail view)
    if st.button("Remove from my selection", key=f"remove_detail_{detail_id}"):

        track_event(
            event="selection_remove_item",
            page="My_Selection",
            props={
                "object_id": detail_id,
                "artist": art.get("principalOrFirstMaker"),
                "had_notes": bool(
                    (st.session_state.get("notes", {}).get(detail_id) or "").strip()
                ),
                "prev_count": len(favorites),
                "origin": "detail_view",
            },
        )

        favorites.pop(detail_id, None)
        st.session_state["favorites"] = favorites

        try:
            with open(FAV_FILE, "w", encoding="utf-8") as f:
                json.dump(favorites, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        if "notes" in st.session_state:
            st.session_state["notes"].pop(detail_id, None)
            try:
                with open(NOTES_FILE, "w", encoding="utf-8") as f:
                    json.dump(
                        st.session_state["notes"],
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )
            except Exception:
                pass

        st.session_state["detail_art_id"] = None

        st.success("Artwork removed from your selection.")
        st.rerun()

    # Close detail panel
    if st.button("Close detail view", key=f"close_detail_{detail_id}"):
        st.session_state["detail_art_id"] = None
        st.rerun()


# ============================================================
# Footer
# ============================================================
show_footer()