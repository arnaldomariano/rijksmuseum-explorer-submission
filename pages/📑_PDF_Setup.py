# pages/📑_PDF_Setup.py
"""
PDF Setup page.

This page configures how the illustrated PDF is generated from the
"My Selection" page. It controls:

- Whether to include a cover page.
- Whether to include a global opening text / introduction.
- Whether to include research notes in each artwork page.
- Whether to include an overview/summary page.
- Whether to include Rijksmuseum “About” text.

Settings are stored in a small JSON file (PDF_META_FILE) and are
shared with the My_Selection page via the same file.
"""

from __future__ import annotations

import json
from typing import Dict, Any

import streamlit as st

from app_paths import PDF_META_FILE, FAV_FILE
from analytics import track_event, track_event_once
from ui_theme import inject_global_css, show_global_footer, show_page_intro


# ============================================================
# Page config & global CSS
# ============================================================
st.set_page_config(page_title="PDF Setup", page_icon="📑", layout="wide")

# Apply the shared dark theme + layout for the whole app
inject_global_css()

# Small local height adjustment so this page aligns with the others
st.markdown(
    """
    <style>
    div.block-container {
        padding-top: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Helpers: default meta, load/save, selection count
# ============================================================
def _default_pdf_meta() -> Dict[str, Any]:
    """
    Return the default PDF configuration structure.

    We keep this small and focused. If older JSON files contain
    extra keys, they are safely ignored.
    """
    return {
        "opening_text": "",
        "include_cover": True,
        "include_opening_text": True,
        "include_notes": True,
        "include_summary": True,  # summary / overview page
        "include_about": True,    # Rijks “About” text block
    }


def load_pdf_meta() -> Dict[str, Any]:
    """
    Load PDF configuration shared with the My_Selection page.

    The result is cached in st.session_state["pdf_meta"] so we
    do not hit the filesystem on every rerun.

    Known keys (all optional in the JSON file):
      - opening_text: str
      - include_cover: bool
      - include_opening_text: bool
      - include_notes: bool
      - include_summary: bool
      - include_about: bool
    """
    # If already in session_state, normalize and return
    if "pdf_meta" in st.session_state:
        meta = st.session_state["pdf_meta"]
        if isinstance(meta, dict):
            base = _default_pdf_meta()
            base.update(meta)
            st.session_state["pdf_meta"] = base
            return base

    # Otherwise, start from defaults and merge with file contents (if any)
    base = _default_pdf_meta()
    if PDF_META_FILE.exists():
        try:
            with open(PDF_META_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            # PDF meta is optional; never break the app here
            pass

    st.session_state["pdf_meta"] = base
    return base


def save_pdf_meta(meta: Dict[str, Any]) -> None:
    """
    Persist PDF configuration to disk and update session_state.

    We always merge with the default structure to guarantee that all
    expected keys exist (including future ones like include_summary).
    """
    base = _default_pdf_meta()
    if isinstance(meta, dict):
        base.update(meta)

    st.session_state["pdf_meta"] = base
    try:
        with open(PDF_META_FILE, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)
    except Exception:
        # Never break the UI because of a save error
        pass


def load_selection_count() -> int:
    """
    Return the number of artworks currently in the global selection.

    It first tries st.session_state["favorites"] (when the user has
    already visited My Selection). If that is not available, it
    falls back to reading the local favorites file.
    """
    favorites = st.session_state.get("favorites")
    if isinstance(favorites, dict):
        return len(favorites)

    try:
        if FAV_FILE.exists():
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return len(data) if isinstance(data, dict) else 0
    except Exception:
        pass

    return 0


# ============================================================
# Analytics — page view (once per session)
# ============================================================
track_event_once(
    event="page_view",
    page="PDF_Setup",
    once_key="page_view::PDF_Setup",
    props={"has_existing_config": PDF_META_FILE.exists()},
)


# ============================================================
# Page header
# ============================================================
# 1) Global intro block (shared visual pattern)
show_page_intro(
    "Use this page to configure how the illustrated PDF is generated from your **My Selection** page.",
    [
        "These options control the PDF created when you click **Prepare PDF** on the My Selection page.",
        "All configuration is stored locally in a small JSON file and never sent anywhere.",
        "You can choose to add a cover page, an opening text and include your research notes and About text.",
    ],
)

# 2) Local page title just below the intro block
st.markdown("## 📑 PDF setup")

# 3) Small pill with current selection size (if available)
selection_count = load_selection_count()
if selection_count:
    st.markdown(
        f'<span class="rijks-pill">Current selection: '
        f'<strong>{selection_count}</strong> artwork(s)</span>',
        unsafe_allow_html=True,
    )


# ============================================================
# Main configuration panel
# ============================================================
pdf_meta = load_pdf_meta()

st.markdown('<div class="rijks-panel">', unsafe_allow_html=True)
st.markdown("### General PDF settings")

include_cover = st.checkbox(
    "Include cover page",
    value=bool(pdf_meta.get("include_cover", True)),
    help="Adds a first page with title, generation date and total number of artworks.",
)

include_opening_text = st.checkbox(
    "Include opening text / introduction",
    value=bool(pdf_meta.get("include_opening_text", True)),
    help="Adds an introductory text section at the beginning of the PDF.",
)

include_notes_flag = st.checkbox(
    "Include research notes in each artwork page",
    value=bool(pdf_meta.get("include_notes", True)),
    help=(
        "When enabled, each artwork page in the PDF will include your notes "
        "from the My Selection page (when available)."
    ),
)

include_summary_flag = st.checkbox(
    "Include selection overview page",
    value=bool(pdf_meta.get("include_summary", True)),
    help="Adds a summary page listing all artworks in your selection.",
)

include_about_flag = st.checkbox(
    "Include artwork description (About)",
    value=bool(pdf_meta.get("include_about", True)),
    help=(
        "If enabled, the PDF will fetch the Rijksmuseum 'About' text for each artwork "
        "and add it as a description block below the image."
    ),
)

opening_text = st.text_area(
    "Opening text (optional introduction)",
    value=pdf_meta.get("opening_text", ""),
    height=200,
    help=(
        "This text appears near the beginning of the PDF as an introduction. "
        "You can describe the purpose of this selection, the research context, "
        "or any narrative you want to add."
    ),
)

st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Save / reset controls
# ============================================================
st.markdown('<div class="rijks-panel">', unsafe_allow_html=True)
st.markdown("### Save or reset PDF configuration")

col_s1, col_s2 = st.columns(2)

with col_s1:
    if st.button("💾 Save PDF configuration", use_container_width=True):
        updated = dict(pdf_meta)
        updated["include_cover"] = bool(include_cover)
        updated["include_opening_text"] = bool(include_opening_text)
        updated["include_notes"] = bool(include_notes_flag)
        updated["include_summary"] = bool(include_summary_flag)
        updated["include_about"] = bool(include_about_flag)
        updated["opening_text"] = opening_text

        save_pdf_meta(updated)

        track_event(
            event="pdf_meta_saved",
            page="PDF_Setup",
            props={
                "opening_text": opening_text,
                "include_cover": bool(include_cover),
                "include_opening_text": bool(include_opening_text),
                "include_notes": bool(include_notes_flag),
                "include_summary": bool(include_summary_flag),
                "include_about": bool(include_about_flag),
            },
        )

        st.success(
            "PDF configuration saved. You can now prepare the PDF on the My Selection page."
        )

with col_s2:
    if st.button("↩️ Reset to default settings", use_container_width=True):
        base = _default_pdf_meta()
        save_pdf_meta(base)

        track_event(
            event="pdf_meta_reset",
            page="PDF_Setup",
            props={},
        )

        st.success("PDF settings reset to defaults.")
        st.rerun()

st.markdown("</div>", unsafe_allow_html=True)


# ============================================================
# Raw JSON (debug / advanced)
# ============================================================
with st.expander("🔍 View raw PDF configuration (advanced)", expanded=False):
    st.json(st.session_state.get("pdf_meta", {}))


# ============================================================
# Footer
# ============================================================
show_global_footer()