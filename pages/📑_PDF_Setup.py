"""
PDF Setup — configure PDF export defaults.

This page edits data/pdf_meta.json (via PDF_META_FILE):
- opening_text
- include_cover
- include_opening_text
- include_notes

PDF generation happens in My Selection page (ReportLab optional).
"""

from __future__ import annotations

import json
import streamlit as st

from app_paths import PDF_META_FILE
from analytics import track_event_once, track_event

from ui_theme import inject_global_css, show_global_footer, show_page_intro

st.set_page_config(page_title="PDF Setup", page_icon="🧾", layout="wide")
st.set_page_config(
    page_title="PDF Setup",
    page_icon="📄",
    layout="wide",
)

inject_global_css()

track_event_once(
    event="page_view",
    page="PDF_Setup",
    once_key="page_view::PDF_Setup",
    props={},
)

show_page_intro(
    "This page configures how PDF exports behave for your current selection.",
    [
        "Checks whether the optional `reportlab` dependency is installed.",
        "Lets you choose basic layout options for PDF exports (page size, margins, thumbnails).",
        "Shows diagnostic information if something is missing in your environment.",
        "Explains how the **My Selection** page will use these settings when preparing a PDF.",
        "All configuration stays local to this device — nothing is sent externally.",
    ],
)

st.markdown("## 🧾 PDF Setup")
st.caption("Configure default options used by the PDF export on My Selection page.")


# ============================================================
# Load / save helpers
# ============================================================
def load_pdf_meta() -> dict:
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
    return base


def save_pdf_meta(meta: dict) -> None:
    try:
        with open(PDF_META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


meta = load_pdf_meta()

# ============================================================
# UI
# ============================================================
st.markdown("### Content")
opening_text = st.text_area(
    "Opening text (optional)",
    value=meta.get("opening_text", ""),
    height=180,
    help="A short introduction shown near the beginning of the PDF.",
)

st.markdown("### Include sections")
include_cover = st.toggle("Include cover page", value=bool(meta.get("include_cover", True)))
include_opening_text = st.toggle("Include opening text section", value=bool(meta.get("include_opening_text", True)))
include_notes = st.toggle("Include research notes", value=bool(meta.get("include_notes", True)))

if st.button("Save PDF settings"):
    meta_updated = {
        "opening_text": opening_text,
        "include_cover": bool(include_cover),
        "include_opening_text": bool(include_opening_text),
        "include_notes": bool(include_notes),
    }
    save_pdf_meta(meta_updated)

    track_event(
        event="pdf_settings_saved",
        page="PDF_Setup",
        props={
            "include_cover": bool(include_cover),
            "include_opening_text": bool(include_opening_text),
            "include_notes": bool(include_notes),
            "opening_text_len": len((opening_text or "").strip()),
        },
    )

    st.success("PDF settings saved.")

# ============================================================
# Footer
# ============================================================
show_global_footer()