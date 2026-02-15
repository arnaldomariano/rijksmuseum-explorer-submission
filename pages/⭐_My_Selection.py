# pages/⭐_My_Selection.py
"""
My Selection — researcher workflow page.

Features:
- Persistent local selection (favorites.json)
- Persistent research notes (notes.json)
- Filter inside the selection (text, year range, artist, notes-only)
- Compare candidates (up to 4) for the Compare Artworks page
- Exports: CSV / JSON / Share code / Notes exports
- Optional PDF export (ReportLab) with simple per-artwork pages
"""

from __future__ import annotations
from ui_theme import inject_global_css, show_global_footer, show_page_intro


import csv
import io
import json
from datetime import datetime
from textwrap import wrap
from typing import Any, Dict, List, Tuple

import requests
import streamlit as st

from app_paths import FAV_FILE, NOTES_FILE, PDF_META_FILE
from analytics import track_event, track_event_once
from rijks_api import (
    get_best_image_url,
    fetch_metadata_by_objectnumber,
    RijksAPIError,
    extract_year,
)

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

def inject_page_css() -> None:
    """CSS específico da página My Selection (cards, badges, export panel)."""
    st.markdown(
        """
        <style>
        .rijks-summary-pill {
            display: inline-block;
            padding: 4px 10px;
            #border-radius: 999px;
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
            #border: 1px solid #262626;
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

        .export-card h4 {
            margin: 0 0 0.4rem 0;
            font-size: 0.95rem;
        }

        .export-card p {
            font-size: 0.8rem;
            color: #c7c7c7;
            margin-bottom: 0.6rem;
        }

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

        .rijks-card-caption {
            font-size: 0.9rem;
            color: #c7c7c7;
            margin-bottom: 0.25rem;
        }

        .rijks-badge-row {
            margin-top: 0.15rem;
            margin-bottom: 0.35rem;
        }

        .rijks-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 0.73rem;
            margin-right: 0.25rem;
            background-color: #262626;
            color: #f5f5f5;
            #border: 1px solid #333333;
        }

        .rijks-badge-primary {
            background-color: #ff9900;
            color: #111111;
            border-color: #ff9900;
        }

        .rijks-badge-secondary {
            background-color: #262626;
            color: #ffddaa;
            border-color: #444444;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

st.set_page_config(page_title="My Selection", page_icon="⭐", layout="wide")

inject_global_css()   # tema base para o app todo
inject_page_css()     # ajustes específicos da My Selection

# ============================================================
# Helpers: favorites / notes
# ============================================================

def _safe_read_json(path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_favorites() -> Dict[str, Any]:
    if "favorites" not in st.session_state:
        if FAV_FILE.exists():
            st.session_state["favorites"] = _safe_read_json(FAV_FILE)
        else:
            st.session_state["favorites"] = {}
    fav = st.session_state["favorites"]
    return fav if isinstance(fav, dict) else {}


def load_notes() -> Dict[str, str]:
    if "notes" not in st.session_state:
        if NOTES_FILE.exists():
            st.session_state["notes"] = _safe_read_json(NOTES_FILE)
        else:
            st.session_state["notes"] = {}
    notes = st.session_state["notes"]
    return notes if isinstance(notes, dict) else {}


def save_favorites(fav: Dict[str, Any]) -> None:
    st.session_state["favorites"] = fav
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(fav, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_notes(notes: Dict[str, str]) -> None:
    st.session_state["notes"] = notes
    try:
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
# Selection stats
# ============================================================


def compute_selection_stats(favorites: Dict[str, Any]) -> Dict[str, Any]:
    years: List[int] = []
    artists: set[str] = set()
    count = 0

    for art in favorites.values():
        if not isinstance(art, dict):
            continue
        count += 1
        maker = art.get("principalOrFirstMaker")
        if isinstance(maker, str) and maker.strip():
            artists.add(maker.strip())
        dating = art.get("dating") or {}
        year = extract_year(dating) if isinstance(dating, dict) else None
        if isinstance(year, int):
            years.append(year)

    stats = {
        "count": count,
        "artists": len(artists),
        "min_year": min(years) if years else None,
        "max_year": max(years) if years else None,
    }
    return stats

def load_pdf_meta() -> Dict[str, Any]:
    """
    Load PDF configuration saved by the PDF Setup page.

    The config file (PDF_META_FILE) stores:
      - include_cover: bool
      - include_opening_text: bool
      - include_notes: bool
      - opening_text: str
    """
    base = {
        "include_cover": True,
        "include_opening_text": True,
        "include_notes": True,
        "include_summary": True,
        "include_about": True,
        "opening_text": "",
    }

    try:
        if PDF_META_FILE.exists():
            with open(PDF_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base.update(data)
    except Exception:
        # If anything goes wrong, we silently fall back to defaults.
        pass

    return base


# ============================================================
# Cached image helper (for faster gallery rendering)
# ============================================================
@st.cache_data(show_spinner=False)
def cached_best_image_url(art: Dict[str, Any]) -> str | None:
    """Small cache wrapper around get_best_image_url for faster gallery rendering."""
    return get_best_image_url(art)


# ============================================================
# Filters
# ============================================================


def passes_filters(
    obj_num: str,
    art: Dict[str, Any],
    notes: Dict[str, str],
    text_filter: str,
    artist_filter: str,
    year_min: int,
    year_max: int,
    notes_mode: str,
) -> bool:
    # Notes mode
    note_text = (notes.get(obj_num, "") or "").strip()
    if notes_mode == "with" and not note_text:
        return False
    if notes_mode == "without" and note_text:
        return False

    # Artist
    if artist_filter.strip():
        artist = (art.get("principalOrFirstMaker") or "").lower()
        if artist_filter.strip().lower() not in artist:
            return False

    # Year range
    dating = art.get("dating") or {}
    year = extract_year(dating) if isinstance(dating, dict) else None
    if isinstance(year, int):
        if year < year_min or year > year_max:
            return False

    # Text search in title/artist/materials/places
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


# ============================================================
# Export helpers
# ============================================================


def build_selection_csv(favorites: Dict[str, Any], notes: Dict[str, str]) -> str:
    rows: List[List[str]] = []
    for obj_num, art in favorites.items():
        if not isinstance(art, dict):
            continue
        title = art.get("title", "")
        maker = art.get("principalOrFirstMaker", "")
        dating = art.get("dating", {}) or {}
        date = dating.get("presentingDate") or dating.get("year") or ""
        link = (art.get("links") or {}).get("web", "")
        has_note = bool((notes.get(obj_num, "") or "").strip())
        rows.append([obj_num, title, maker, str(date), link, str(has_note)])

    if not rows:
        return ""

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["objectNumber", "title", "artist", "date", "web_link", "has_notes"])
    w.writerows(rows)
    return buf.getvalue()


def build_notes_csv(notes: Dict[str, str]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["objectNumber", "note"])
    for obj_num, text in notes.items():
        if isinstance(text, str) and text.strip():
            w.writerow([obj_num, text.strip()])
    return buf.getvalue()


def build_share_code(favorites: Dict[str, Any]) -> str:
    """
    Minimal share code: JSON with list of objectNumbers.
    (Podemos sofisticar depois se você quiser carregar coleções completas.)
    """
    ids = sorted([obj for obj in favorites.keys() if isinstance(obj, str)])
    payload = {"objectNumbers": ids, "generated_at": datetime.utcnow().isoformat()}
    return json.dumps(payload, ensure_ascii=False)

def build_pdf_buffer(
    favorites: Dict[str, Any],
    notes: Dict[str, str],
    pdf_meta: Dict[str, Any],
) -> bytes:
    """
    Illustrated PDF controlled by PDF Setup options.

    - Optional cover page with selection summary
    - Optional index/summary page ("Selection overview")
    - Optional opening text / introduction
    - One page per artwork:
        title, artist, objectNumber, date, web link, thumbnail
    - Optional Rijksmuseum “About” text block
    - Optional research notes at the bottom of each artwork page
    - Global footer on every page (app name + page number)
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab not available")

    # --------------------------------------------------------
    # Layout constants (ajustes finos de espaçamento e fontes)
    # --------------------------------------------------------
    PAGE_MARGIN = 50
    TITLE_WRAP = 70           # largura para quebrar título da obra
    BODY_WRAP = 88            # largura para textos gerais
    ABOUT_WRAP = 86           # largura para About
    NOTES_WRAP = 86           # largura para Notes

    COVER_TITLE_SIZE = 22
    SECTION_TITLE_SIZE = 18
    ARTWORK_TITLE_SIZE = 15
    META_FONT_SIZE = 11
    BODY_FONT_SIZE = 10
    FOOTER_FONT_SIZE = 8

    # --------------------------------------------------------
    # Helper: fetch Rijks "About" text with a tiny in-memory cache
    # --------------------------------------------------------
    about_cache: Dict[str, str] = {}

    def get_about_text(obj_num: str) -> str:
        """
        Return the Rijksmuseum 'About' text for this object, if available.

        Works with the linked-data detail JSON (like the SK-A-4273 file),
        where the description usually lives in the `referred_to_by` list.
        """
        # Cache em memória para não bater na API toda hora
        if obj_num in about_cache:
            return about_cache[obj_num]

        # Chama a API de detalhe
        try:
            detail = fetch_metadata_by_objectnumber(obj_num)
        except RijksAPIError:
            about_cache[obj_num] = ""
            return ""
        except Exception:
            about_cache[obj_num] = ""
            return ""

        if not isinstance(detail, dict):
            about_cache[obj_num] = ""
            return ""

        # 1) Formato novo: pegar o maior texto em `referred_to_by[*].content`
        best = ""
        referred = detail.get("referred_to_by") or []
        if isinstance(referred, list):
            for entry in referred:
                if not isinstance(entry, dict):
                    continue
                content = (entry.get("content") or "").strip()
                if content and len(content) > len(best):
                    best = content

        # 2) Fallback para formatos antigos (artObject / top-level description)
        if not best:
            art_obj = detail.get("artObject") or {}
            best = (
                art_obj.get("plaqueDescriptionEnglish")
                or art_obj.get("description")
                or detail.get("plaqueDescriptionEnglish")
                or detail.get("description")
                or ""
            )

        best = (best or "").strip()
        about_cache[obj_num] = best
        return best

    # --------------------------------------------------------
    # Options coming from PDF Setup
    # --------------------------------------------------------
    include_cover = bool(pdf_meta.get("include_cover", True))
    include_opening_text = bool(pdf_meta.get("include_opening_text", True))
    include_notes = bool(pdf_meta.get("include_notes", True))
    include_summary = bool(pdf_meta.get("include_summary", True))
    include_about = bool(pdf_meta.get("include_about", True))
    opening_text = (pdf_meta.get("opening_text") or "").strip()

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = PAGE_MARGIN

    # Running page counter (for footer)
    page_num = 1

    def draw_footer() -> None:
        """Draw a small footer at the bottom of the current page."""
        nonlocal page_num
        c.setFont("Helvetica", FOOTER_FONT_SIZE)
        c.setFillGray(0.5)
        footer_text = f"Rijksmuseum Explorer — research selection · page {page_num}"
        c.drawCentredString(width / 2, margin / 2, footer_text)
        c.setFillGray(0.0)

    # --------------------------------------------------------
    # Stable list of items ordered by artist, then title
    # --------------------------------------------------------
    items: List[Tuple[str, Dict[str, Any]]] = [
        (obj, art) for obj, art in favorites.items() if isinstance(art, dict)
    ]

    def sort_key(item: Tuple[str, Dict[str, Any]]):
        """Sort by artist, then title, then objectNumber."""
        obj_num, art = item
        artist = (art.get("principalOrFirstMaker") or "").lower()
        title = (art.get("title") or "").lower()
        return (artist, title, obj_num)

    items.sort(key=sort_key)

    # --------------------------------------------------------
    # Optional cover page
    # --------------------------------------------------------
    if include_cover:
        stats = compute_selection_stats(favorites)

        c.setFont("Helvetica-Bold", COVER_TITLE_SIZE)
        c.drawString(margin, height - margin - 20, "Rijksmuseum Explorer — Selection")

        c.setFont("Helvetica", META_FONT_SIZE)
        y = height - margin - 60
        c.drawString(
            margin,
            y,
            f"Generated at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        )
        y -= 20
        c.drawString(margin, y, f"Artworks in selection: {stats.get('count', 0)}")
        y -= 20
        c.drawString(margin, y, f"Distinct artists: {stats.get('artists', 0)}")

        min_y = stats.get("min_year")
        max_y = stats.get("max_year")
        if min_y and max_y:
            y -= 20
            if min_y == max_y:
                c.drawString(margin, y, f"Approximate date: around {min_y}")
            else:
                c.drawString(margin, y, f"Approximate date range: {min_y}–{max_y}")

        draw_footer()
        c.showPage()
        page_num += 1

    # --------------------------------------------------------
    # Optional summary / index page
    # --------------------------------------------------------
    if include_summary and items:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, height - margin - 20, "Selection overview")

        # Fonte base do corpo da tabela
        c.setFont("Helvetica", 10)
        y = height - margin - 50

        # Column positions
        x_id = margin
        # Empurramos título e artista 15 pontos para a direita
        x_title = margin + 100
        x_artist = margin + 315
        x_date = width - margin - 70  # deixa espaço à direita

        # Header row (um pouco mais forte)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(x_id, y, "Object ID")
        c.drawString(x_title, y, "Title")
        c.drawString(x_artist, y, "Artist")
        c.drawString(x_date, y, "Date")

        # Volta para a fonte normal para as linhas da tabela
        c.setFont("Helvetica", 10)
        y -= 16

        for obj_num, art in items:
            if y < margin + 40:
                draw_footer()
                c.showPage()
                page_num += 1

                c.setFont("Helvetica-Bold", 14)
                c.drawString(margin, height - margin - 20, "Selection overview (cont.)")

                # Fonte base do corpo da tabela
                c.setFont("Helvetica", 10)
                y = height - margin - 50

                # Header row (continuação, mesmo estilo da página 1)
                c.setFont("Helvetica-Bold", 11)
                c.drawString(x_id, y, "Object ID")
                c.drawString(x_title, y, "Title")
                c.drawString(x_artist, y, "Artist")
                c.drawString(x_date, y, "Date")

                # Volta para a fonte normal para as linhas da tabela
                c.setFont("Helvetica", 10)
                y -= 16

            title = art.get("title") or "Untitled"
            maker = art.get("principalOrFirstMaker") or "Unknown artist"
            dating = art.get("dating") or {}
            year = extract_year(dating) if isinstance(dating, dict) else None
            date_full = dating.get("presentingDate") or (str(year) if year else "")

            # ======= TRUNCAMENTOS =======

            # Object ID: limita para não encostar no título
            obj_id_display = obj_num
            if len(obj_id_display) > 15:
                obj_id_display = obj_id_display[:14] + "…"

            # Título: um pouco menor para caber melhor
            if len(title) > 40:
                title = title[:37] + "..."

            # Artista: corta mais cedo para não pegar a coluna de data
            if len(maker) > 20:
                maker = maker[:17] + "..."

            # Data: só os primeiros 10 caracteres (ex.: '1675-01-01')
            date_str = date_full[:10]

            # ======= DESENHO DAS COLUNAS =======
            c.drawString(x_id, y, obj_id_display)
            c.drawString(x_title, y, title)
            c.drawString(x_artist, y, maker)
            c.drawString(x_date, y, date_str)
            y -= 14
        draw_footer()
        c.showPage()
        page_num += 1

    # --------------------------------------------------------
    # Optional opening text / introduction
    # --------------------------------------------------------
    if include_opening_text and opening_text:
        c.setFont("Helvetica-Bold", SECTION_TITLE_SIZE)
        c.drawString(margin, height - margin - 20, "Introduction")

        c.setFont("Helvetica", META_FONT_SIZE)
        y = height - margin - 60
        wrapped_intro = wrap(opening_text, width=80)  # antes era 90
        for line in wrapped_intro:
            if y < margin + 40:
                draw_footer()
                c.showPage()
                page_num += 1
                c.setFont("Helvetica", META_FONT_SIZE)
                y = height - margin
            c.drawString(margin, y, line)
            y -= 14

        draw_footer()
        c.showPage()
        page_num += 1

    # --------------------------------------------------------
    # One page per artwork
    # --------------------------------------------------------
    for obj_num, art in items:
        title = art.get("title") or "Untitled"
        maker = art.get("principalOrFirstMaker") or "Unknown artist"
        dating = art.get("dating") or {}
        year = extract_year(dating) if isinstance(dating, dict) else None
        date_str = dating.get("presentingDate") or (str(year) if year else "")
        link = (art.get("links") or {}).get("web", "")

        # Header: título da obra com quebra de linha
        c.setFont("Helvetica-Bold", ARTWORK_TITLE_SIZE)
        y = height - margin - 15
        title_lines = wrap(title, width=TITLE_WRAP) or ["Untitled"]
        for line in title_lines:
            c.drawString(margin, y, line)
            y -= 17

        # Metadados (artista, data, object number)
        c.setFont("Helvetica", META_FONT_SIZE)
        y -= 4
        c.drawString(margin, y, f"Artist: {maker}")
        y -= 16
        if date_str:
            c.drawString(margin, y, f"Date: {date_str}")
            y -= 16
        c.drawString(margin, y, f"Object number: {obj_num}")
        y -= 18

        # Link (se existir)
        if link:
            c.setFont("Helvetica-Oblique", BODY_FONT_SIZE - 1)
            short_link = link[:80]
            c.drawString(margin, y, f"Rijksmuseum (web): {short_link}")
            y -= 20

        # Thumbnail
        img_url = get_best_image_url(art)
        if img_url:
            try:
                resp = requests.get(img_url, timeout=8)
                if resp.ok:
                    img_data = io.BytesIO(resp.content)
                    img = ImageReader(img_data)

                    max_w = width - 2 * margin
                    max_h = 240   # um pouco menor para sobrar espaço p/ texto
                    iw, ih = img.getSize()
                    scale = min(max_w / iw, max_h / ih)
                    img_w = iw * scale
                    img_h = ih * scale
                    img_x = margin
                    img_y = y - img_h
                    c.drawImage(
                        img,
                        img_x,
                        img_y,
                        width=img_w,
                        height=img_h,
                        preserveAspectRatio=True,
                    )
                    y = img_y - 18

                    # pequena linha de separação visual
                    c.setLineWidth(0.3)
                    c.line(margin, y + 6, width - margin, y + 6)
                    y -= 10
            except Exception:
                # Ignore image errors; continue with text-only page
                pass

        # ----------------------------------------------------
        # About text from Rijksmuseum (if available)
        # ----------------------------------------------------
        if include_about:
            about_text = get_about_text(obj_num)
            if about_text:
                c.setFont("Helvetica-Bold", META_FONT_SIZE)
                if y < margin + 60:
                    # Not enough space for heading + algumas linhas
                    draw_footer()
                    c.showPage()
                    page_num += 1
                    y = height - margin
                c.drawString(margin, y, "About this artwork (Rijksmuseum):")
                y -= 14

                c.setFont("Helvetica", BODY_FONT_SIZE)
                for line in wrap(about_text, width=ABOUT_WRAP):
                    if y < margin + 40:
                        draw_footer()
                        c.showPage()
                        page_num += 1
                        c.setFont("Helvetica", BODY_FONT_SIZE)
                        y = height - margin
                    # leve recuo para o bloco de texto
                    c.drawString(margin + 10, y, line)
                    y -= 12

                y -= 6  # pequeno respiro antes das notas

        # ----------------------------------------------------
        # Notes (only if enabled in PDF Setup)
        # ----------------------------------------------------
        note_text = (notes.get(obj_num, "") or "").strip()
        if include_notes and note_text:
            # Se estiver muito perto do rodapé, pula de página antes de abrir o bloco
            if y < margin + 70:
                draw_footer()
                c.showPage()
                page_num += 1
                y = height - margin

            # Pequeno espaço extra antes do título "Notes:"
            y -= 4

            c.setFont("Helvetica-Bold", 11)
            c.drawString(margin, y, "Notes:")
            y -= 14

            c.setFont("Helvetica", 10)
            wrapped_notes = wrap(note_text, width=90)
            for line in wrapped_notes:
                if y < margin + 40:
                    draw_footer()
                    c.showPage()
                    page_num += 1
                    c.setFont("Helvetica", 10)
                    y = height - margin
                c.drawString(margin, y, line)
                y -= 12

        # Close last page for this artwork
        draw_footer()
        c.showPage()
        page_num += 1

    c.save()
    buf.seek(0)
    return buf.getvalue()

# ============================================================
# Compare candidates helpers
# ============================================================


def get_compare_candidates(fav: Dict[str, Any]) -> List[str]:
    return [
        obj for obj, art in fav.items() if isinstance(art, dict) and art.get("_compare_candidate")
    ]


def set_compare_candidate(favorites: Dict[str, Any], obj_num: str, desired: bool) -> None:
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
# Page header & data load
# ============================================================

show_page_intro(
    "This page shows the user's saved artworks (local favorites). It provides:",
    [
        "Local persistence of favorites and research notes (JSON files).",
        "Internal filters (metadata and notes) over the current selection.",
        "Gallery controls (sorting, grouping by artist, compact mode, pagination).",
        "Export tools (CSV / JSON / PDF, selection-sharing code, notes exports).",
        "Artwork comparison (side-by-side) within the current selection.",
        "Detail view for a single artwork with zoom and research notes editor.",
        "Local analytics events for usage statistics (no data is sent anywhere).",
    ],
)

# Título + texto explicativo do legacy
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

favorites = load_favorites()
notes = load_notes()

# Analytics — page view (only once)
if "analytics_my_selection_viewed" not in st.session_state:
    st.session_state["analytics_my_selection_viewed"] = True
    track_event_once(
        event="page_view",
        page="My_Selection",
        once_key="page_view::My_Selection",
        props={
            "has_favorites": bool(favorites),
            "favorites_count": len(favorites) if isinstance(favorites, dict) else 0,
        },
    )

if not favorites:
    st.info(
        "You currently have no artworks in your selection. "
        "Go to the **Rijksmuseum Explorer** page and mark "
        "**In my selection** on any artwork you want to keep."
    )
    show_global_footer()
    st.stop()

# ============================================================
# Summary pill + insights
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
                "- **Approximate date range:** "
                f"from **{stats['min_year']}** to **{stats['max_year']}**"
            )
    else:
        st.write("- **Date range:** not available from API metadata.")

# ============================================================
# Sidebar controls (filters, sorting, gallery options)
# ============================================================

default_min_year = stats["min_year"] if stats["min_year"] is not None else 1400
default_max_year = stats["max_year"] if stats["max_year"] is not None else 2025

# One-time sidebar tip state
if "sidebar_tip_dismissed" not in st.session_state:
    st.session_state["sidebar_tip_dismissed"] = False

with st.sidebar:
    st.markdown("## 🔧 My Selection Controls")

    # One-time hint to collapse the sidebar
    if not st.session_state.get("sidebar_tip_dismissed", False):
        with st.container():
            st.info(
                "💡 Tip: You can collapse this panel using the « icon on the top left.",
                icon="ℹ️",
            )
            if st.button("Got it", key="dismiss_sidebar_tip"):
                st.session_state["sidebar_tip_dismissed"] = True
                st.rerun()

    # Internal metadata filters (inside selection)
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

    selection_filter_label = st.radio(
        "Show in gallery:",
        options=[
            f"All artworks ({total_artworks})",
            f"Only artworks with notes ({total_with_notes})",
            f"Only artworks without notes ({total_without_notes})",
        ],
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

group_by_artist = (gallery_view == "Group by artist")
cards_per_row = 5 if compact_mode else 3

filters_active = any(
    [
        text_filter.strip(),
        artist_filter.strip(),
        object_type_filter.strip(),
        (year_min, year_max) != (default_min_year, default_max_year),
    ]
)

# ============================================================
# Apply internal metadata filters to favorites
# ============================================================

filtered_favorites: Dict[str, Any] = favorites

if filters_active:
    filtered_favorites = {
        obj_num: art
        for obj_num, art in favorites.items()
        if passes_filters(
            obj_num=obj_num,
            art=art,
            notes=notes,
            text_filter=text_filter,
            artist_filter=artist_filter,
            year_min=year_min,
            year_max=year_max,
            # Notes filter handled later (with/without/all)
            notes_mode="any",
        )
        and (
            not object_type_filter.strip()
            or object_type_filter.strip().lower()
            in ", ".join(art.get("objectTypes") or []).lower()
        )
    }

    st.caption(
        f"Showing {len(filtered_favorites)} of {len(favorites)} artworks "
        f"after internal metadata filters."
    )
else:
    st.caption(
        "No internal metadata filter applied (showing all artworks in your selection)."
    )

# ============================================================
# Export panel (keeping the newer panel style)
# ============================================================

pdf_meta = load_pdf_meta()  # <-- NEW: read PDF settings saved on PDF Setup

st.markdown('<div class="rijks-export-panel">', unsafe_allow_html=True)
st.markdown("### Export & share selection")

csv_data = build_selection_csv(favorites, notes)
notes_csv_data = build_notes_csv(notes)
favorites_json_pretty = json.dumps(favorites, ensure_ascii=False, indent=2)
favorites_json_compact = json.dumps(favorites, ensure_ascii=False, separators=(",", ":"))

collection_code = build_share_code(favorites)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>CSV</h4>", unsafe_allow_html=True)
    st.markdown("<p>Table format for Excel/Sheets.</p>", unsafe_allow_html=True)
    if csv_data:
        if st.download_button(
            "📄 Download CSV",
            csv_data,
            "rijks_selection.csv",
            "text/csv",
            key="ms_dl_csv",
        ):
            track_event(
                event="export_download",
                page="My_Selection",
                props={"format": "csv", "scope": "selection", "count": len(favorites)},
            )
    else:
        st.caption("No data available yet.")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>JSON</h4>", unsafe_allow_html=True)
    st.markdown("<p>For scripts, apps and APIs.</p>", unsafe_allow_html=True)
    if st.download_button(
        "🧾 Download JSON (pretty)",
        favorites_json_pretty,
        "rijks_selection_pretty.json",
        "application/json",
        key="ms_dl_json_pretty",
    ):
        track_event(
            event="export_download",
            page="My_Selection",
            props={"format": "json", "scope": "selection", "count": len(favorites)},
        )
    if st.download_button(
        "🧾 Download JSON (compact)",
        favorites_json_compact,
        "rijks_selection.json",
        "application/json",
        key="ms_dl_json_compact",
    ):
        track_event(
            event="export_download",
            page="My_Selection",
            props={"format": "json_compact", "scope": "selection", "count": len(favorites)},
        )
    st.markdown("</div>", unsafe_allow_html=True)

with col3:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>PDF</h4>", unsafe_allow_html=True)
    st.markdown("<p>Printable report of your selection.</p>", unsafe_allow_html=True)

    # Small human-readable summary of current PDF profile
    include_cover_ui = bool(pdf_meta.get("include_cover", True))
    include_opening_text_ui = bool(pdf_meta.get("include_opening_text", True))
    include_notes_ui = bool(pdf_meta.get("include_notes", True))
    include_summary_ui = bool(pdf_meta.get("include_summary", True))
    include_about_ui = bool(pdf_meta.get("include_about", True))

    flags = []
    if include_cover_ui:
        flags.append("cover")
    if include_opening_text_ui:
        flags.append("opening text")
    if include_summary_ui:
        flags.append("overview page")
    if include_about_ui:
        flags.append("about text")
    if include_notes_ui:
        flags.append("notes")

    if flags:
        st.caption("Current PDF setup: " + ", ".join(flags))
    else:
        st.caption("Current PDF setup: none (very minimal PDF).")

    if "pdf_buffer" not in st.session_state:
        st.session_state["pdf_buffer"] = None

    if st.button("Prepare PDF", key="ms_prepare_pdf"):
        if not REPORTLAB_AVAILABLE:
            st.warning("Install `reportlab` to enable PDF export.")
        else:
            with st.spinner("Preparing PDF..."):
                # <-- NEW: pass pdf_meta
                st.session_state["pdf_buffer"] = build_pdf_buffer(
                    favorites, notes, pdf_meta
                )
                track_event(
                    event="export_prepare",
                    page="My_Selection",
                    props={"format": "pdf", "count": len(favorites)},
                )

    # If a PDF buffer is available, show download button
    if st.session_state.get("pdf_buffer"):
        if st.download_button(
            "📑 Download PDF",
            st.session_state["pdf_buffer"],
            "rijks_selection.pdf",
            "application/pdf",
            key="ms_dl_pdf",
        ):
            track_event(
                event="export_download",
                page="My_Selection",
                props={"format": "pdf", "scope": "selection", "count": len(favorites)},
            )

    st.markdown("</div>", unsafe_allow_html=True)

with col4:
    st.markdown('<div class="export-card">', unsafe_allow_html=True)
    st.markdown("<h4>Share & notes</h4>", unsafe_allow_html=True)
    st.markdown(
        "<p>Share your selection and export research notes.</p>",
        unsafe_allow_html=True,
    )

    with st.expander("🔗 Share selection code", expanded=False):
        st.caption("Copy this code to share your selection with another user:")
        st.code(collection_code, language=None)

    with st.expander("📝 Export notes", expanded=False):
        if notes_csv_data:
            st.download_button(
                "📄 Download notes (CSV)",
                notes_csv_data,
                "rijks_notes.csv",
                "text/csv",
                key="ms_dl_notes_csv",
            )
        else:
            st.caption("No notes available yet.")
        st.download_button(
            "🧾 Download notes (JSON)",
            json.dumps(notes, ensure_ascii=False, indent=2),
            "rijks_notes.json",
            "application/json",
            key="ms_dl_notes_json",
        )

    st.markdown("</div>", unsafe_allow_html=True)

# ============================================================
# Clear entire selection (como no legacy)
# ============================================================

if st.button("Clear my entire selection"):
    # Clear favorites in memory and on disk
    st.session_state["favorites"] = {}
    favorites = {}
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    # Reset compare candidates and PDF buffer
    st.session_state["compare_candidates"] = []
    st.session_state["pdf_buffer"] = None
    st.session_state["detail_art_id"] = None

    st.success("Your selection has been cleared.")
    st.rerun()

# ============================================================
# Gallery + comparison logic (grid + group-by-artist, legacy-style)
# ============================================================

def get_year_for_sort(art: Dict[str, Any]) -> int | None:
    """Return a numeric year for sorting (when available)."""
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
    txt = notes.get(obj_num, "")
    return isinstance(txt, str) and txt.strip() != ""


def has_note(obj_id: str) -> bool:
    txt = notes.get(obj_id, "")
    return isinstance(txt, str) and txt.strip() != ""


def get_compare_candidates_from_favorites(fav: Dict[str, Any]) -> List[str]:
    """Return objectNumbers marked as comparison candidates inside favorites."""
    return [
        obj_num
        for obj_num, art in fav.items()
        if isinstance(art, dict) and art.get("_compare_candidate")
    ]


# Base items = favorites after metadata filters
base_items: List[Tuple[str, Dict[str, Any]]] = list(filtered_favorites.items())

# Global sorting over base_items
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

# Filter by keyword inside notes
if note_filter_lower:
    base_items = [
        (obj_num, art)
        for obj_num, art in base_items
        if note_filter_lower in (notes.get(obj_num, "") or "").lower()
    ]

# High-level filter: with / without notes
if selection_filter_code == "with_notes":
    base_items = [(obj_num, art) for obj_num, art in base_items if has_note(obj_num)]
elif selection_filter_code == "without_notes":
    base_items = [(obj_num, art) for obj_num, art in base_items if not has_note(obj_num)]

# Summary after all filters (metadata + notes)
total_after_filters = len(base_items)
artists_after_filters = len(
    {(art.get("principalOrFirstMaker") or "Unknown artist") for _, art in base_items}
)

st.caption(
    f"Current view: **{total_after_filters}** artwork(s) "
    f"from **{artists_after_filters}** artist(s) after all filters."
)

if not base_items:
    st.info(
        "No artworks match the current filters "
        "(metadata filters, notes keyword and notes status)."
    )

else:
    # Human-readable summary of active filters
    filters_summary: List[str] = []
    if filters_active:
        if text_filter.strip():
            filters_summary.append(f"text contains '{text_filter.strip()}'")
        if (year_min, year_max) != (default_min_year, default_max_year):
            filters_summary.append(f"year between {year_min}-{year_max}")
        if artist_filter.strip():
            filters_summary.append(f"artist contains '{artist_filter.strip()}'")
        if object_type_filter.strip():
            filters_summary.append(f"object type contains '{object_type_filter.strip()}'")
    if selection_filter_code == "with_notes":
        filters_summary.append("only artworks with notes")
    elif selection_filter_code == "without_notes":
        filters_summary.append("only artworks without notes")
    if note_filter_lower:
        filters_summary.append(f"notes contain '{note_filter}'")
    filters_summary.append("view: group by artist" if group_by_artist else "view: grid")

    if filters_summary:
        st.caption("Active filters: " + " · ".join(filters_summary))
    else:
        st.caption("Active filters: none (full selection).")

    # --------------------------------------------------------
    # Cross-page comparison candidates: summary, filter & clear
    # --------------------------------------------------------

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

            for obj_num in candidate_ids:
                art = favorites.get(obj_num, {})
                title = art.get("title", "Untitled")
                maker = art.get("principalOrFirstMaker", "Unknown artist")
                st.markdown(f"- **{title}** — *{maker}*  \n`{obj_num}`")

            show_only_cmp = st.checkbox(
                "Show only these artworks in the gallery below",
                key="show_only_cmp_checkbox",
            )

            if st.button("Clear all comparison marks", key="clear_all_cmp"):
                for obj_num in candidate_ids:
                    art = favorites.get(obj_num)
                    if isinstance(art, dict):
                        art.pop("_compare_candidate", None)
                        favorites[obj_num] = art
                st.session_state["favorites"] = favorites
                try:
                    with open(FAV_FILE, "w", encoding="utf-8") as f:
                        json.dump(favorites, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                st.session_state["compare_candidates"] = []
                st.success("All comparison marks have been cleared.")
                st.rerun()
    else:
        st.caption("No artworks are currently marked for cross-page comparison.")

    if show_only_cmp and candidate_ids:
        base_items = [
            (obj_num, art) for obj_num, art in base_items if obj_num in candidate_ids
        ]
        total_after_filters = len(base_items)
        st.caption(
            f"Gallery restricted to **{total_after_filters}** comparison candidate(s)."
        )

    # =========================================================
    # Card rendering helper (shared by grid and grouped view)
    # =========================================================

    if "cmp_limit_warning" not in st.session_state:
        st.session_state["cmp_limit_warning"] = False
    if "cmp_key_generation" not in st.session_state:
        st.session_state["cmp_key_generation"] = 0

    def handle_compare_logic(obj_num: str, desired: bool) -> None:
        """
        Atualiza o status de comparação de um artwork.
        - Garante no máximo 4 candidatos.
        - Atualiza favorites[obj_num]['_compare_candidate'].
        - Persiste em disco.
        """
        art = favorites.get(obj_num)
        if not isinstance(art, dict):
            return

        is_candidate = bool(art.get("_compare_candidate"))
        current_candidates = get_compare_candidates_from_favorites(favorites)

        if desired and not is_candidate:
            if len(current_candidates) >= 4:
                st.session_state["cmp_limit_warning"] = True
                st.session_state["cmp_key_generation"] = (
                    st.session_state.get("cmp_key_generation", 0) + 1
                )
                st.rerun()
                return
            art["_compare_candidate"] = True

        elif not desired and is_candidate:
            art.pop("_compare_candidate", None)
        else:
            return

        favorites[obj_num] = art
        st.session_state["favorites"] = favorites
        try:
            with open(FAV_FILE, "w", encoding="utf-8") as f:
                json.dump(favorites, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def render_cards(items: List[Tuple[str, Dict[str, Any]]], allow_compare: bool) -> None:
        for start_idx in range(0, len(items), cards_per_row):
            row_items = items[start_idx : start_idx + cards_per_row]
            cols = st.columns(len(row_items))

            for col, (obj_num, art) in zip(cols, row_items):
                with col:
                    note_for_this = notes.get(obj_num, "")
                    has_notes_flag = isinstance(note_for_this, str) and note_for_this.strip()

                    card_classes = "rijks-card"
                    if has_notes_flag:
                        card_classes += " rijks-card-has-notes"
                    else:
                        card_classes += " rijks-card-no-notes"
                    if art.get("_compare_candidate"):
                        card_classes += " rijks-card-compare-candidate"

                    st.markdown(
                        f'<div class="{card_classes}">', unsafe_allow_html=True
                    )

                    # Thumbnail
                    if show_images:
                        img_url = cached_best_image_url(art)
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

                    web_link = (art.get("links") or {}).get("web")
                    dating = art.get("dating") or {}
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

                    # Extra metadata
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

                    # Compare checkbox
                    if allow_compare and obj_num:
                        is_candidate = bool(art.get("_compare_candidate"))
                        cmp_gen = st.session_state.get("cmp_key_generation", 0)
                        cmp_key = f"cmp_candidate_{obj_num}_{cmp_gen}"
                        checked = st.checkbox(
                            "Mark for comparison",
                            key=cmp_key,
                            value=is_candidate,
                        )
                        if checked != is_candidate:
                            handle_compare_logic(obj_num, checked)

                    # Detail view button
                    if st.button("View details", key=f"detail_btn_{obj_num}"):
                        st.session_state["detail_art_id"] = obj_num

                    # Remove from selection
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
                                    (notes.get(obj_num, "") or "").strip()
                                ),
                                "prev_count": len(favorites),
                                "origin": "card",
                            },
                        )
                        favorites.pop(obj_num, None)
                        st.session_state["favorites"] = favorites
                        try:
                            with open(FAV_FILE, "w", encoding="utf-8") as f:
                                json.dump(favorites, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass

                        if st.session_state.get("detail_art_id") == obj_num:
                            st.session_state["detail_art_id"] = None

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

        grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
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

        def sort_items_for_artist(items_for_artist: List[Tuple[str, Dict[str, Any]]]) -> None:
            if sort_within_artist == "Title (A–Z)":
                items_for_artist.sort(
                    key=lambda it: (
                        it[1].get("title", ""),
                        it[1].get("principalOrFirstMaker", ""),
                    )
                )
            elif sort_within_artist == "Year (oldest → newest)":
                items_for_artist.sort(
                    key=lambda it: (
                        get_year_for_sort(it[1]) is None,
                        get_year_for_sort(it[1]) or 10**9,
                    )
                )
            elif sort_within_artist == "Year (newest → oldest)":
                items_for_artist.sort(
                    key=lambda it: (
                        get_year_for_sort(it[1]) is None,
                        -(get_year_for_sort(it[1]) or -10**9),
                    )
                )
            elif sort_within_artist == "Notes first":
                items_for_artist.sort(
                    key=lambda it: (
                        not has_note_text(it[0]),
                        it[1].get("title", ""),
                    )
                )

        for artist in page_artists:
            items_for_artist = grouped.get(artist, [])
            sort_items_for_artist(items_for_artist)

            years = [get_year_for_sort(a) for _, a in items_for_artist]
            years = [y for y in years if isinstance(y, int)]
            min_y = min(years) if years else None
            max_y = max(years) if years else None
            notes_count = sum(1 for obj_id, _ in items_for_artist if has_note_text(obj_id))

            subtitle_parts = [
                f"{len(items_for_artist)} artwork(s)",
                f"{notes_count} with notes",
            ]
            if min_y and max_y:
                subtitle_parts.append(f"{min_y}–{max_y}")

            header_line = " • ".join(subtitle_parts)

            with st.expander(
                f"👤 {artist} — {header_line}", expanded=expand_artists
            ):
                render_cards(items_for_artist, allow_compare=enable_compare_grouped)

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

        st.markdown(
            "### Mark artworks from your selection as comparison candidates"
        )

        render_cards(page_items, allow_compare=True)

        if st.session_state.get("cmp_limit_warning"):
            st.warning(
                "You can mark at most 4 artworks for comparison. "
                "Unmark another one first."
            )
            st.session_state["cmp_limit_warning"] = False

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
# Detail view + research notes editor (legacy style)
# ============================================================

detail_id = st.session_state.get("detail_art_id")
if detail_id and detail_id in favorites:
    art = favorites[detail_id]

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
    web_link = (art.get("links") or {}).get("web")
    dating = art.get("dating") or {}
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
    existing_note = notes.get(detail_id, "")
    note_text = st.text_area(
        "Write your notes for this artwork:",
        value=existing_note,
        height=160,
        key=f"note_{detail_id}",
    )

    if st.button("Save notes", key=f"save_note_{detail_id}"):
        notes[detail_id] = note_text
        save_notes(notes)
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

    if st.button("Remove from my selection", key=f"remove_detail_{detail_id}"):
        track_event(
            event="selection_remove_item",
            page="My_Selection",
            props={
                "object_id": detail_id,
                "artist": art.get("principalOrFirstMaker"),
                "had_notes": bool((notes.get(detail_id, "") or "").strip()),
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

        notes.pop(detail_id, None)
        save_notes(notes)

        st.session_state["detail_art_id"] = None
        st.success("Artwork removed from your selection.")
        st.rerun()

    if st.button("Close detail view", key=f"close_detail_{detail_id}"):
        st.session_state["detail_art_id"] = None
        st.rerun()

# ============================================================
# Footer
# ============================================================
show_global_footer()