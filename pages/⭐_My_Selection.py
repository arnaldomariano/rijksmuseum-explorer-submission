# pages/⭐_My_Selection.py
"""
My Selection — researcher workflow page.

Features:
- Persistent local selection (favorites.json)
- Persistent research notes (notes.json)
- Filter inside the selection (text + notes-only)
- Compare candidates (up to 4) for Compare Artworks page
- Exports: CSV / JSON / Share code / Notes exports
- Optional PDF export (ReportLab) with thumbnails + notes
- Detail view with zoom and notes editor

DEV_MODE:
- Hidden by default. If DEV_MODE=true in secrets.toml, shows raw Linked Art JSON for debugging.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime
from textwrap import wrap
from typing import Any, Dict, List, Tuple

import requests
import streamlit as st

from app_paths import FAV_FILE, NOTES_FILE, PDF_META_FILE
from analytics import track_event
from rijks_api import get_best_image_url, fetch_metadata_by_objectnumber, RijksAPIError

DEV_MODE = bool(st.secrets.get("DEV_MODE", False))


# ============================================================
# Optional PDF dependency (ReportLab)
# ============================================================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False


# ============================================================
# Page config & CSS
# ============================================================
st.set_page_config(page_title="My Selection", page_icon="⭐", layout="wide")


def inject_custom_css() -> None:
    """Dark mode + cards + export panel styling."""
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

        section[data-testid="stSidebar"] { background-color: #181818 !important; }

        div[data-testid="stMarkdownContainer"] a {
            color: #ff9900 !important;
            text-decoration: none;
        }
        div[data-testid="stMarkdownContainer"] a:hover { text-decoration: underline; }

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
            height: 250px;
            object-fit: cover;
            border-radius: 8px;
        }

        .rijks-card-title { font-size: 0.95rem; font-weight: 600; margin-top: 0.5rem; color: #f1f1f1; }
        .rijks-card-caption { font-size: 0.8rem; color: #b8b8b8; margin-bottom: 0.25rem; }

        .cmp-pill {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.75rem;
            background-color: #101010;
            border: 1px solid #333333;
            color: #ffb347;
            margin-top: 0.35rem;
        }

        .rijks-footer {
            margin-top: 2.5rem;
            padding-top: 0.75rem;
            border-top: 1px solid #262626;
            font-size: 0.8rem;
            color: #aaaaaa;
            text-align: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_footer() -> None:
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
# Persistence helpers
# ============================================================
def load_favorites() -> Dict[str, Any]:
    """Load favorites dict from disk into session_state."""
    if "favorites" in st.session_state and isinstance(st.session_state["favorites"], dict):
        return st.session_state["favorites"]

    if FAV_FILE.exists():
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state["favorites"] = data if isinstance(data, dict) else {}
        except Exception:
            st.session_state["favorites"] = {}
    else:
        st.session_state["favorites"] = {}

    return st.session_state["favorites"]


def save_favorites(favorites: Dict[str, Any]) -> None:
    """Persist favorites to disk and session_state."""
    st.session_state["favorites"] = favorites
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favorites, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_notes() -> Dict[str, str]:
    """Load notes dict from disk into session_state."""
    if "notes" in st.session_state and isinstance(st.session_state["notes"], dict):
        return st.session_state["notes"]

    if NOTES_FILE.exists():
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state["notes"] = data if isinstance(data, dict) else {}
        except Exception:
            st.session_state["notes"] = {}
    else:
        st.session_state["notes"] = {}

    return st.session_state["notes"]


def save_notes(notes: Dict[str, str]) -> None:
    """Persist notes to disk and session_state."""
    st.session_state["notes"] = notes
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
# Cached helpers
# ============================================================
@st.cache_data(show_spinner=False)
def cached_best_image_url(art: dict) -> str | None:
    return get_best_image_url(art)


@st.cache_data(show_spinner=False)
def cached_fetch_metadata(object_number: str) -> dict:
    return fetch_metadata_by_objectnumber(object_number)


# ============================================================
# PDF meta config (optional)
# ============================================================
def load_pdf_meta() -> dict:
    """Load PDF meta configuration shared with PDF setup page (if any)."""
    if "pdf_meta" in st.session_state:
        return st.session_state["pdf_meta"]

    base = {
        "opening_text": "",
        "include_cover": True,
        "include_opening_text": True,
        "include_notes": True,
    }

    if PDF_META_FILE.exists():
        try:
            with open(PDF_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass

    st.session_state["pdf_meta"] = base
    return base


# ============================================================
# Optional PDF builder
# ============================================================
def build_pdf_buffer(favorites: Dict[str, Any], notes: Dict[str, str]) -> bytes | None:
    """
    Build an illustrated PDF report (one artwork per page).
    Includes thumbnails (best-effort) and research notes.
    """
    if not REPORTLAB_AVAILABLE or not favorites:
        return None

    pdf_meta = load_pdf_meta()
    include_cover = bool(pdf_meta.get("include_cover", True))
    include_opening_text = bool(pdf_meta.get("include_opening_text", True))
    include_notes_flag = bool(pdf_meta.get("include_notes", True))
    opening_text = (pdf_meta.get("opening_text") or "").strip()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    margin_left, margin_right = 50, 50
    margin_top = page_h - 80
    margin_bottom = 60

    def footer():
        c.setFont("Helvetica", 8)
        left = f"Rijksmuseum Explorer — My selection ({len(favorites)} artworks)"
        right = f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        c.drawString(margin_left, margin_bottom, left)
        c.drawRightString(page_w - margin_right, margin_bottom, right)

    def draw_text_block(title: str, text: str, y: float, cont_header: str) -> float:
        text = (text or "").strip()
        if not text:
            return y

        if y < margin_bottom + 40:
            footer()
            c.showPage()
            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin_left, margin_top, cont_header)
            y = margin_top - 30

        c.setFont("Helvetica-Oblique", 11)
        c.drawString(margin_left, y, title)
        y -= 18

        c.setFont("Helvetica", 10)
        for line in wrap(text, width=90):
            if y < margin_bottom + 20:
                footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 12)
                c.drawString(margin_left, margin_top, cont_header)
                y = margin_top - 30
                c.setFont("Helvetica", 10)
            c.drawString(margin_left, y, line)
            y -= 14

        return y

    total = len(favorites)

    # Cover
    if include_cover:
        c.setFont("Helvetica-Bold", 24)
        c.drawString(margin_left, page_h - 180, "Rijksmuseum Explorer — My selection")

        c.setFont("Helvetica", 11)
        c.drawString(margin_left, page_h - 220, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.drawString(margin_left, page_h - 238, f"{total} artwork(s) in this selection")

        footer()
        c.showPage()

    # Opening text
    if include_opening_text and opening_text:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin_left, margin_top, "Introduction")

        y = margin_top - 35
        c.setFont("Helvetica", 11)
        for line in wrap(opening_text, width=90):
            if y < margin_bottom + 20:
                footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 16)
                c.drawString(margin_left, margin_top, "Introduction (cont.)")
                y = margin_top - 35
                c.setFont("Helvetica", 11)
            c.drawString(margin_left, y, line)
            y -= 15

        footer()
        c.showPage()

    # Contents page
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
                footer()
                c.showPage()
                c.setFont("Helvetica-Bold", 16)
                c.drawString(margin_left, margin_top, "Contents (cont.)")
                y = margin_top - 35
                c.setFont("Helvetica", 11)
            c.drawString(margin_left, y, wrapped_line)
            y -= 15

    footer()
    c.showPage()

    # One artwork per page
    for idx, (obj_num, art) in enumerate(favorites.items(), start=1):
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin_left, margin_top, "Rijksmuseum Selection")
        c.setFont("Helvetica", 11)
        c.drawString(margin_left, margin_top - 24, f"Artwork {idx} of {total}")

        title = art.get("title", "Untitled")
        maker = art.get("principalOrFirstMaker", "Unknown artist")
        dating = art.get("dating", {}) or {}
        date = dating.get("presentingDate") or dating.get("year") or ""
        link = (art.get("links") or {}).get("web", "")

        img_url = get_best_image_url(art)

        thumb_w, thumb_h = 170, 170
        x_img = margin_left
        y_img_top = margin_top - 80
        x_text = x_img + thumb_w + 25
        y_text = y_img_top

        drawn = False
        if img_url:
            try:
                resp = requests.get(img_url, timeout=8)
                resp.raise_for_status()
                img_data = io.BytesIO(resp.content)
                img_reader = ImageReader(img_data)

                iw, ih = img_reader.getSize()
                ratio = min(thumb_w / iw, thumb_h / ih)
                draw_w, draw_h = iw * ratio, ih * ratio

                c.drawImage(
                    img_reader,
                    x_img,
                    y_img_top - draw_h,
                    width=draw_w,
                    height=draw_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
                drawn = True
            except Exception:
                drawn = False

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
            c.drawString(x_text, y_text, f"Link: {link.replace('https://', '')}")

        y_cursor = (y_img_top - thumb_h - 40) if drawn else (y_text - 28)
        y_cursor = min(y_cursor, y_text - 28)

        if include_notes_flag:
            note_text = (notes.get(obj_num, "") or "").strip()
            y_cursor = draw_text_block("Research notes:", note_text, y_cursor, f"Notes (cont.) — {obj_num}")

        footer()
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


# ============================================================
# Page header
# ============================================================
st.markdown("## ⭐ My selection")
st.write(
    "This page shows all artworks saved in your selection. Selections and notes are stored locally on this device. "
    "You can filter within your selection, manage notes, export data and open a detail view for each artwork."
)

favorites = load_favorites()
notes = load_notes()

if not favorites:
    st.info("You currently have no artworks in your selection. Go to the Explorer page and add some artworks first.")
    show_footer()
    st.stop()


# ============================================================
# Sidebar controls
# ============================================================
with st.sidebar:
    st.markdown("## 🔧 My Selection Controls")

    text_filter = st.text_input("Search in title / artist / metadata", value="", key="ms_text_filter")
    only_with_notes = st.toggle("Only artworks with notes", value=False, key="ms_only_notes")
    show_thumbnails = st.toggle("Show thumbnails", value=True, key="ms_show_thumbs")

    st.markdown("### PDF export")
    if not REPORTLAB_AVAILABLE:
        st.caption("PDF export is disabled (install `reportlab` to enable it).")


# ============================================================
# Filter selection items
# ============================================================
def passes_filters(obj_num: str, art: Dict[str, Any]) -> bool:
    if only_with_notes and not (notes.get(obj_num, "") or "").strip():
        return False

    if text_filter.strip():
        needle = text_filter.strip().lower()
        parts: List[str] = []

        for k in ("title", "longTitle", "principalOrFirstMaker"):
            v = art.get(k)
            if isinstance(v, str):
                parts.append(v.lower())

        for k in ("materials", "techniques", "productionPlaces"):
            v = art.get(k) or []
            if isinstance(v, list):
                parts.extend(str(x).lower() for x in v)

        if needle not in " | ".join(parts):
            return False

    return True


items: List[Tuple[str, Dict[str, Any]]] = [(k, v) for k, v in favorites.items() if isinstance(v, dict)]
items = [(obj_num, art) for obj_num, art in items if passes_filters(obj_num, art)]

st.markdown(f'<div class="rijks-summary-pill">Saved artworks: <strong>{len(favorites)}</strong></div>', unsafe_allow_html=True)
st.caption(f"Current view: **{len(items)}** artwork(s) after filters.")


# ============================================================
# Export panel (researcher-friendly)
# ============================================================
st.markdown('<div class="rijks-export-panel">', unsafe_allow_html=True)
st.markdown("### Export & share selection")

# Build CSV
rows: List[List[str]] = []
for obj_num, art in favorites.items():
    title = art.get("title", "")
    maker = art.get("principalOrFirstMaker", "")
    dating = art.get("dating", {}) or {}
    date = dating.get("presentingDate") or dating.get("year") or ""
    link = (art.get("links") or {}).get("web", "")
    has_note = bool((notes.get(obj_num, "") or "").strip())
    rows.append([obj_num, title, maker, str(date), link, str(has_note)])

csv_data = None
if rows:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["objectNumber", "title", "artist", "date", "web_link", "has_notes"])
    w.writerows(rows)
    csv_data = buf.getvalue()

favorites_json_pretty = json.dumps(favorites, ensure_ascii=False, indent=2)
favorites_json_compact = json.dumps(favorites, ensure_ascii=False)
collection_code = base64.b64encode(favorites_json_compact.encode("utf-8")).decode("ascii")

# Notes export
notes_rows: List[List[str]] = []
for obj_num, art in favorites.items():
    txt = (notes.get(obj_num, "") or "").strip()
    if not txt:
        continue
    notes_rows.append([obj_num, art.get("title", ""), art.get("principalOrFirstMaker", ""), txt])

notes_csv_data = None
if notes_rows:
    buf2 = io.StringIO()
    w2 = csv.writer(buf2)
    w2.writerow(["objectNumber", "title", "artist", "note"])
    w2.writerows(notes_rows)
    notes_csv_data = buf2.getvalue()

notes_json = json.dumps(notes, ensure_ascii=False, indent=2)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>CSV</h4>", unsafe_allow_html=True)
    st.markdown("<p>Table format for Excel/Sheets.</p>", unsafe_allow_html=True)
    if csv_data:
        st.download_button("📄 Download CSV", csv_data, "rijks_selection.csv", "text/csv", key="ms_dl_csv")
    else:
        st.caption("No data.")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>JSON</h4>", unsafe_allow_html=True)
    st.markdown("<p>For scripts, apps and APIs.</p>", unsafe_allow_html=True)
    st.download_button("🧾 Download JSON", favorites_json_pretty, "rijks_selection.json", "application/json", key="ms_dl_json")
    st.markdown("</div>", unsafe_allow_html=True)

with col3:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>PDF</h4>", unsafe_allow_html=True)
    st.markdown("<p>Printable report (optional).</p>", unsafe_allow_html=True)

    if "pdf_buffer" not in st.session_state:
        st.session_state["pdf_buffer"] = None

    if st.button("Prepare PDF", key="ms_prepare_pdf"):
        if not REPORTLAB_AVAILABLE:
            st.warning("Install `reportlab` to enable PDF export.")
        else:
            with st.spinner("Preparing PDF..."):
                st.session_state["pdf_buffer"] = build_pdf_buffer(favorites, notes)

            track_event(event="export_prepare", page="My_Selection", props={"format": "pdf", "count": len(favorites)})

    if st.session_state.get("pdf_buffer"):
        st.download_button("📑 Download PDF", st.session_state["pdf_buffer"], "rijks_selection.pdf", "application/pdf", key="ms_dl_pdf")
        track_event(event="export_download", page="My_Selection", props={"format": "pdf", "count": len(favorites)})

    st.markdown("</div>", unsafe_allow_html=True)

with col4:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>Share & notes</h4>", unsafe_allow_html=True)
    st.markdown("<p>Share selection + export notes.</p>", unsafe_allow_html=True)

    with st.expander("🔗 Share selection code", expanded=False):
        st.caption("Copy this code to share your selection with another user:")
        st.code(collection_code, language=None)

    with st.expander("📝 Export notes", expanded=False):
        if notes_csv_data:
            st.download_button("📄 Download notes (CSV)", notes_csv_data, "rijks_notes.csv", "text/csv", key="ms_dl_notes_csv")
        else:
            st.caption("No notes available yet.")
        st.download_button("🧾 Download notes (JSON)", notes_json, "rijks_notes.json", "application/json", key="ms_dl_notes_json")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Compare candidates (up to 4)
# ============================================================
if "cmp_key_generation" not in st.session_state:
    st.session_state["cmp_key_generation"] = 0


def get_compare_candidates(fav: Dict[str, Any]) -> List[str]:
    return [obj for obj, a in fav.items() if isinstance(a, dict) and a.get("_compare_candidate")]


def set_compare_candidate(obj_num: str, desired: bool) -> None:
    art = favorites.get(obj_num)
    if not isinstance(art, dict):
        return
    if desired:
        art["_compare_candidate"] = True
    else:
        art.pop("_compare_candidate", None)
    favorites[obj_num] = art
    save_favorites(favorites)


# ============================================================
# Gallery
# ============================================================
st.markdown("### Gallery")

cards_per_row = 3
for start in range(0, len(items), cards_per_row):
    row = items[start:start + cards_per_row]
    cols = st.columns(len(row))

    for col, (obj_num, art) in zip(cols, row):
        with col:
            st.markdown('<div class="rijks-card">', unsafe_allow_html=True)

            if show_thumbnails:
                img_url = cached_best_image_url(art)
                if img_url:
                    st.image(img_url, use_container_width=True)
                else:
                    st.caption("No public image available in current mapping.")

            st.markdown(f'<div class="rijks-card-title">{art.get("title", "Untitled")}</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="rijks-card-caption">{art.get("principalOrFirstMaker", "Unknown artist")}</div>', unsafe_allow_html=True)

            # Compare candidate checkbox (max 4)
            current = get_compare_candidates(favorites)
            is_candidate = bool(art.get("_compare_candidate"))

            key_gen = st.session_state.get("cmp_key_generation", 0)
            cmp_key = f"cmp_candidate_{obj_num}_{key_gen}"
            desired = st.checkbox("Mark for comparison", value=is_candidate, key=cmp_key)

            if desired != is_candidate:
                if desired and len(current) >= 4:
                    st.warning("You can mark at most 4 artworks for comparison.")
                    st.session_state["cmp_key_generation"] = key_gen + 1
                    st.rerun()
                set_compare_candidate(obj_num, desired)

            if is_candidate:
                st.markdown('<span class="cmp-pill">🎯 Candidate</span>', unsafe_allow_html=True)

            # Detail view button
            if st.button("View details", key=f"detail_btn_{obj_num}"):
                st.session_state["detail_art_id"] = obj_num
                st.rerun()

            # Remove from selection
            if st.button("Remove from my selection", key=f"remove_{obj_num}"):
                favorites.pop(obj_num, None)
                notes.pop(obj_num, None)
                save_favorites(favorites)
                save_notes(notes)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Detail view (if selected)
# ============================================================
detail_id = st.session_state.get("detail_art_id")
if detail_id and detail_id in favorites:
    art = favorites[detail_id]

    st.markdown("---")
    st.subheader("🔍 Detail view")

    col_img, col_meta = st.columns([3, 2])

    with col_img:
        img_url = get_best_image_url(art)
        if img_url:
            zoom = st.slider("Zoom (relative size)", min_value=50, max_value=200, value=120, step=10, key=f"zoom_{detail_id}")
            st.image(img_url, width=int(700 * zoom / 100))
        else:
            st.caption("No public image available in current mapping.")

    with col_meta:
        st.write(f"**Title:** {art.get('title', 'Untitled')}")
        st.write(f"**Artist:** {art.get('principalOrFirstMaker', 'Unknown artist')}")
        st.write(f"**Object ID:** {detail_id}")

        dating = art.get("dating") or {}
        date = dating.get("presentingDate") or dating.get("year")
        if date:
            st.write(f"**Date:** {date}")

        link = (art.get("links") or {}).get("web")
        if link:
            st.markdown(f"[View on Rijksmuseum website]({link})")

        # DEV-only: raw metadata
        if DEV_MODE:
            with st.expander("DEV: Raw Linked Art JSON", expanded=False):
                try:
                    raw = cached_fetch_metadata(detail_id)
                    st.json(raw)
                except RijksAPIError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    st.markdown("### 📝 Research notes")
    existing_note = notes.get(detail_id, "")
    note_text = st.text_area("Write your notes for this artwork:", value=existing_note, height=160, key=f"note_{detail_id}")

    if st.button("Save notes", key=f"save_note_{detail_id}"):
        notes[detail_id] = note_text
        save_notes(notes)
        st.success("Notes saved.")

        track_event(event="note_saved", page="My_Selection", props={"object_id": detail_id, "note_len": len(note_text.strip())})

    if st.button("Close detail view", key=f"close_detail_{detail_id}"):
        st.session_state["detail_art_id"] = None
        st.rerun()


# ============================================================
# Footer
# ============================================================
show_footer()