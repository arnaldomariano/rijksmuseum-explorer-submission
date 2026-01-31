# pages/i_About.py
"""
About / How to use — Rijksmuseum Explorer (research-oriented)

This page explains:
- What the app does
- Which Rijksmuseum services it uses (Data Services + Linked Art)
- Research features (authorship scope, selection, notes, compare, exports)
- How to use the app step-by-step
- Local storage and Streamlit Cloud considerations
"""

from __future__ import annotations

import streamlit as st


# ============================================================
# Page config
# ============================================================
st.set_page_config(page_title="About", page_icon="ℹ️", layout="wide")


# ============================================================
# CSS (keep consistent with the rest of the app)
# ============================================================
def inject_custom_css() -> None:
    """Dark theme + centered content for the About page."""
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #111111;
            color: #f5f5f5;
        }

        div.block-container {
            max-width: 900px;
            padding-top: 1.5rem;
            padding-bottom: 3rem;
        }

        section[data-testid="stSidebar"] {
            background-color: #181818 !important;
        }

        div[data-testid="stMarkdownContainer"] a {
            color: #ff9900 !important;
            text-decoration: none;
        }
        div[data-testid="stMarkdownContainer"] a:hover {
            text-decoration: underline;
        }

        h1, h2, h3 { font-weight: 600; }

        .about-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background-color: #262626;
            color: #f5f5f5;
            font-size: 0.85rem;
            margin-top: 0.5rem;
            margin-bottom: 1rem;
        }
        .about-pill strong { color: #ff9900; }

        ul { padding-left: 1.2rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()


# ============================================================
# About
# ============================================================
st.markdown("## ℹ️ About this app")

st.write(
    "The **Rijksmuseum Explorer** is a research-oriented prototype designed to help users "
    "browse, study, filter and compare artworks from the Rijksmuseum collection. "
    "It focuses on a workflow that is useful for students, teachers and researchers: "
    "**search → filter by authorship scope → save a selection → write notes → compare → export**."
)

st.markdown(
    '<div class="about-pill"><strong>Status:</strong> Prototype for study, research and demonstration purposes</div>',
    unsafe_allow_html=True,
)

# (1) DEV_MODE disclaimer (short, museum-friendly)
st.caption("Developer tools are hidden by default.")

st.markdown("### Who is this app for?")
st.write(
    "- Researchers exploring artists, themes, provenance and attribution.\n"
    "- Students learning to navigate museum data and metadata.\n"
    "- Teachers building small curated selections for lessons.\n"
    "- Anyone interested in Dutch art and cultural linked data."
)

st.markdown("### Data sources and credits")
st.write(
    "This prototype uses the **Rijksmuseum Data Services**, including:\n\n"
    "- **Search API** (Data Services): to retrieve candidate items for a query.\n"
    "- **Linked Art resolver** (Linked Data / JSON-LD): to dereference each item and obtain structured metadata.\n\n"
    "Images are displayed using the public image URLs derived from the museum’s linked data (IIIF-based sources). "
    "For full rights, zoom and authoritative information, always refer to the Rijksmuseum website."
)

st.info(
    "This project is an independent prototype and is **not** an official product of the Rijksmuseum. "
    "All rights to artworks, descriptions and images remain with the Rijksmuseum and respective rights holders."
)

st.markdown("### Privacy and storage")
st.write(
    "- Your selection (favorites) and research notes are stored **locally** in small JSON files.\n"
    "- Analytics events (if enabled) are recorded **locally only** (no external tracking).\n"
    "- No personal data is intentionally collected.\n"
)

st.caption(
    "Streamlit Cloud note: the filesystem can be ephemeral. Local files may reset when the app restarts. "
    "For a production-grade version, persistence could be implemented via a database or user download/upload."
)


# ============================================================
# How to use
# ============================================================
st.markdown("---")
st.markdown("## 🧭 How to use this app")

st.markdown("### 1) Explorer (main page)")
st.write(
    "1. Use the sidebar **Search term** to search for an artist, title keyword or theme (e.g., `Rembrandt`, `Brazil`, `self-portrait`).\n"
    "2. Choose a **Fetch up to** limit (how many items to retrieve from the Data Services before local pagination).\n"
    "3. Choose **Authorship scope**:\n"
    "   - **Direct + Attributed (recommended)**: balanced research default.\n"
    "   - **Direct only**: strict authorship (attributed works are hidden).\n"
    "   - **Include workshop/circle/after**: broader research scope.\n"
    "   - **Show all (including unknown)**: maximum coverage.\n"
    "4. Use **Pagination (local)** to browse results page-by-page.\n"
    "5. Optionally apply the year range and text filters (material/place) if metadata is available.\n"
    "6. Click **Apply filters & search**."
)

# (2) Explicit clarification about local pagination = fetched set
st.caption(
    "Pagination is **local**: it browses the filtered results within the set you fetched. "
    "To access more items, increase **Fetch up to** and run the search again."
)

st.markdown("### 2) Saving a selection")
st.write(
    "1. In each artwork card, tick **In my selection** to save it.\n"
    "2. Your selection is used across pages (My Selection, Compare, exports).\n"
    "3. The pill at the top shows how many artworks you currently saved."
)

st.markdown("### 3) Authorship scope (research feature)")
st.write(
    "Each artwork receives an authorship tag based on Linked Art attribution cues:\n\n"
    "- ✅ **Direct**\n"
    "- 🟡 **Attributed**\n"
    "- 🟠 **Workshop**\n"
    "- 🔵 **Circle/School**\n"
    "- 🟣 **After**\n"
    "- ⚪ **Unknown**\n\n"
    "Use **Authorship scope** to include/exclude categories depending on your research question."
)

st.markdown("### 4) My Selection (notes, export and detail view)")
st.write(
    "1. Open **My Selection**.\n"
    "2. Filter within your saved artworks (text filter, notes-only filter).\n"
    "3. Click **View details** on an artwork to open a larger view and write research notes.\n"
    "4. Export your selection as **CSV/JSON**, export notes as **CSV/JSON**, and optionally generate a **PDF** report."
)

st.markdown("### 5) Comparing artworks")
st.write(
    "Comparison is a two-step process:\n\n"
    "1. In **My Selection**, mark up to **4** artworks as comparison candidates.\n"
    "2. Open **Compare Artworks**, choose **exactly 2** items, and the app will show them side-by-side."
)

st.markdown("### 6) PDF export")
st.write(
    "If `reportlab` is installed, the app can generate a PDF report:\n\n"
    "- One artwork per page\n"
    "- Basic metadata\n"
    "- Thumbnail (best effort)\n"
    "- Your research notes (optional, configurable)\n\n"
    "You can configure PDF defaults in the **PDF Setup** page."
)

st.markdown("---")
st.markdown("## 💡 Practical tips")
st.write(
    "- Use **Authorship scope** to avoid wasting time with indirect attributions when you need strict authorship.\n"
    "- Use **notes** to record hypotheses, sources, and cross-references.\n"
    "- For high-resolution zoom and official licensing info, always open the artwork on the Rijksmuseum website.\n"
    "- If you deploy on Streamlit Cloud, treat local storage as temporary unless you add persistence."
)

# (3) Final line: encourage Fetch up to
st.caption("For best results, increase **Fetch up to**.")