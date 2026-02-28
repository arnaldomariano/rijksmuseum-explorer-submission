# pages/i_About.py
"""
About / How to use — Rijksmuseum Explorer (research-oriented)

This page explains:
- What the app does and who it is for
- Which Rijksmuseum services it uses (Data Services + Linked Art + IIIF)
- Research features (authorship scope, selection, notes, compare, exports)
- How to use the app step-by-step
- Local storage, analytics and Streamlit Cloud considerations
"""

from __future__ import annotations

import streamlit as st
from ui_theme import inject_global_css, show_global_footer, show_page_intro


# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="About — Rijksmuseum Explorer",
    page_icon="ℹ️",
    layout="wide",
)

# Global dark theme and base layout
inject_global_css()


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

        /* Standard page-intro block (same pattern as other pages) */
        .page-intro-wrapper {
            margin-bottom: 1.2rem;
        }

        .page-intro-title {
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 0.35rem;
        }

        .page-intro-list {
            margin-top: 0.1rem;
            margin-bottom: 0;
            padding-left: 1.3rem;
            font-size: 0.9rem;
            color: #d4d4d4;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()

# Intro block (standard helper used in all pages)
show_page_intro(
    "This page explains the goals and limitations of the Rijksmuseum Explorer prototype:",
    [
        "It is a personal research tool, not an official Rijksmuseum product.",
        "All data and images come from the Rijksmuseum Data Services and Linked Art resolver.",
        "Favorites, notes and analytics counters are stored locally on your device.",
        "No personal data or research activity is sent to external servers.",
        "The interface is designed for iterative research and experimentation.",
    ],
)

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

st.caption("Developer-oriented tools and debug helpers are hidden by default.")

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
    "Public images are displayed using IIIF-style URLs derived from the museum’s linked data. "
    "For full zoom, rights information and authoritative descriptions, always refer to the Rijksmuseum website."
)

st.info(
    "This project is an independent prototype and is **not** an official product of the Rijksmuseum. "
    "All rights to artworks, descriptions and images remain with the Rijksmuseum and respective rights holders."
)

st.markdown("### Privacy, storage and statistics")
st.write(
    "- Your selection (favorites) and research notes are stored **locally** in small JSON files.\n"
    "- Usage analytics events are also recorded **locally only** in a JSONL file; "
    "the **Statistics** page reads this file to show simple counters and top lists.\n"
    "- No personal data is intentionally collected and no tracking data is sent to remote servers.\n"
)

st.caption(
    "Streamlit Cloud note: the filesystem can be ephemeral. Local files may reset when the app restarts. "
    "For a production-grade version, persistence could be implemented via a database or explicit "
    "download/upload of selections."
)

# ============================================================
# How to use
# ============================================================
st.markdown("---")
st.markdown("## 🧭 How to use this app")

st.markdown("### 1) Explorer (main page)")
st.write(
    "1. Use the sidebar **Search term** to search for an artist, title keyword or theme "
    "(for example: `Rembrandt`, `Brazil`, `self-portrait`).\n"
    "2. Choose a **Fetch up to** limit (how many items to retrieve from Data Services before local pagination).\n"
    "3. Choose **Authorship scope**:\n"
    "   - **Direct + Attributed (recommended)** – balanced research default.\n"
    "   - **Direct only** – strict authorship (attributed works are hidden).\n"
    "   - **Direct + Attributed + Circle (A+C)** – include circle/school but still exclude workshop/after.\n"
    "   - **Include workshop/circle/after** – broadest art-historical context.\n"
    "   - **Show all (including unknown)** – maximum coverage, including unclear cases.\n"
    "4. Use **Pagination (local)** to browse results page by page.\n"
    "5. Optionally apply the year range and text filters (material/place) when metadata is available.\n"
    "6. Click **Apply filters & search**."
)

st.caption(
    "Pagination is **local**: it browses the filtered results within the set you fetched. "
    "To access more items, increase **Fetch up to** and run the search again."
)

st.markdown("### 2) Saving a selection")
st.write(
    "1. In each artwork card, tick **In my selection** to save it.\n"
    "2. Your selection is shared across pages (Explorer, My Selection, Compare, PDF Setup).\n"
    "3. The pill at the top of the Explorer page shows how many artworks you currently saved."
)

st.markdown("### 3) Authorship scope and badges")
st.write(
    "Each artwork receives an authorship tag based on Linked Art attribution cues:\n\n"
    "- ✅ **Direct**\n"
    "- 🟡 **Attributed**\n"
    "- 🟠 **Workshop**\n"
    "- 🔵 **Circle / School**\n"
    "- 🟣 **After**\n"
    "- ⚪ **Unknown**\n\n"
    "The Explorer and My Selection pages display a small badge for this tag. "
    "Use **Authorship scope** in the sidebar to include or exclude categories depending on your research question "
    "(for example, focusing only on direct works when building a strict corpus)."
)

st.markdown("### 4) Image availability and work-type badges")
st.write(
    "The app also shows helper badges about image and work type:\n\n"
    "- **Original work / reproduction / photograph** – inferred from roles and metadata where possible.\n"
    "- **Image status** badges:\n"
    "  - 🔒 *Copyright* – the public image is not available due to rights restrictions.\n"
    "  - ⚠️ *Page missing* – the public object page appears to be unavailable.\n"
    "  - ⚠️ *Image unavailable* – the image endpoint is not responding.\n"
    "  - 🚫 *No public image* – no public IIIF endpoint was found.\n\n"
    "These badges are best-effort hints to guide your research; for authoritative information, "
    "always check the Rijksmuseum website."
)

st.markdown("### 5) My Selection (notes, export and detail view)")
st.write(
    "1. Open **My Selection** to see all artworks saved as favorites.\n"
    "2. Filter within your selection (text filter, year range, object type, notes-only filters).\n"
    "3. Use **Grid** or **Group by artist** view to adapt the gallery to your research style.\n"
    "4. Click **View details** on an artwork to open a larger image and write research notes.\n"
    "5. Export your selection as **CSV/JSON**, export notes as **CSV/JSON**, and optionally generate a **PDF** report."
)

st.markdown("### 6) Comparing artworks")
st.write(
    "Comparison is a two-step process:\n\n"
    "1. In **My Selection**, mark up to **4** artworks as comparison candidates using "
    "the **Mark for comparison** checkbox.\n"
    "2. Open **Compare Artworks**, choose **exactly 2** items, and the app will show them side by side "
    "with synchronized basic metadata."
)

st.markdown("### 7) PDF export")
st.write(
    "If the `reportlab` library is installed, the app can generate an illustrated PDF report:\n\n"
    "- Optional cover and overview (index) pages with basic statistics.\n"
    "- One page per artwork with title, artist, object number, date and web link.\n"
    "- A thumbnail image (best effort, using the same image URLs as the app).\n"
    "- Optional Rijksmuseum “About this artwork” text (when available via Linked Art).\n"
    "- Optional research notes written in **My Selection**.\n\n"
    "You can configure these options on the **PDF Setup** page before generating the report."
)

st.markdown("---")
st.markdown("## 💡 Practical tips")
st.write(
    "- Use **Authorship scope** to avoid spending time on indirect attributions when you need strict authorship.\n"
    "- Use **notes** to record hypotheses, sources, cross-references and open questions.\n"
    "- For high-resolution zoom and licensing information, always open the artwork on the Rijksmuseum website.\n"
    "- If you deploy on Streamlit Cloud, treat local storage as temporary unless you add a persistent backend.\n"
    "- Use the **Statistics** page to inspect local usage patterns (searches, page views, export counts)."
)

st.caption("For best coverage, increase **Fetch up to** when running broader searches.")

# ============================================================
# Footer
# ============================================================
show_global_footer()