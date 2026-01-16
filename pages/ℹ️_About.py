import streamlit as st

# ============================================================
# Custom CSS for the About / How to use page
# ============================================================
def inject_custom_css() -> None:
    """
    Inject custom CSS to keep the About page visually consistent
    with the rest of the app (dark theme + centered content).
    """
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

        h1, h2, h3 {
            font-weight: 600;
        }

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
        .about-pill strong {
            color: #ff9900;
        }

        ul {
            padding-left: 1.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_css()

# ============================================================
# About / How to use this app
# ============================================================

st.markdown("## ℹ️ About this app")

st.write(
    "The **Rijksmuseum Explorer** is a personal prototype designed to make it easier "
    "to browse, study and compare artworks from the Rijksmuseum collection. "
    "It uses the public Rijksmuseum API to search artworks and display images "
    "together with key metadata in a research-friendly layout."
)

st.markdown(
    '<div class="about-pill">'
    '<strong>Status:</strong> Prototype for study, teaching and demonstration purposes'
    "</div>",
    unsafe_allow_html=True,
)

st.markdown("### Who is this app for?")

st.write(
    "- Students and researchers exploring specific artists, themes or periods.\n"
    "- Teachers building small curated selections of artworks for a class.\n"
    "- Anyone interested in Dutch art and in experimenting with cultural data and APIs."
)

st.markdown("### Data source and credits")

st.write(
    "All data and images displayed in this app come from the **Rijksmuseum API**. "
    "This app does not store or redistribute images; it only displays the image URLs "
    "returned by the API for each artwork. For full image rights, zoom and official "
    "information, you should always refer to the Rijksmuseum website."
)

st.info(
    "This project is an independent prototype and is **not** an official product of "
    "the Rijksmuseum. All rights to artworks, descriptions and images remain with "
    "the Rijksmuseum and respective rights holders."
)

st.markdown("### Privacy and local storage")

st.write(
    "- Your personal selection of artworks is stored **locally** in a small file "
    "named `favorites.json` in the app folder.\n"
    "- Your **research notes** (written on the *My selection* page) are stored "
    "locally in a file named `notes.json`.\n"
    "- PDF configuration (opening text, whether to include notes/comments, etc.) "
    "is stored locally in a small `pdf_meta.json` file.\n"
    "- These files are used only so your selection, notes and PDF preferences can be "
    "restored when you reopen the app.\n"
    "- No data is sent to any external service other than the Rijksmuseum API itself."
)

st.markdown("---")
st.markdown("## 🧭 How to use this app")

st.markdown("### 1. Rijksmuseum Explorer (main page)")

st.write(
    "1. Use the **sidebar filters** to set a search term (for example `Rembrandt`, "
    "`Post`, `Brazil`, etc.).\n"
    "2. Optionally choose an **object type** (painting, print, drawing, sculpture, photo) "
    "and a sort order.\n"
    "3. Click **“Apply filters & search”** to load artworks that match your criteria.\n"
    "4. Each result shows a thumbnail, title, artist and object ID, plus a link to the "
    "official page on the Rijksmuseum website.\n"
    "5. Use the checkbox **“In my selection”** to mark artworks you want to keep in your "
    "personal collection for later review.\n"
    "6. Your selection is automatically saved locally so it can be restored when you "
    "reopen the app."
)

st.caption(
    "Tip: use the checkbox **“In my selection”** in each card to build your personal "
    "selection, then review, annotate and export it on the **My selection** page."
)

st.markdown("### 2. My selection page")

st.write(
    "1. Open the **My selection** page from the sidebar.\n"
    "2. You will see how many artworks are currently saved and a gallery of your selection.\n"
    "3. Use the **sidebar panel** to filter **inside your selection**, for example by:\n"
    "   - metadata (text search, year range, artist name, object type),\n"
    "   - notes status (only artworks with notes / without notes),\n"
    "   - keywords that appear in your research notes.\n"
    "4. You can choose between **Grid view** and **Group by artist**, and adjust how many "
    "artworks or artists are displayed per page.\n"
    "5. Each card shows the image, title, artist, date (when available) and object ID.\n"
    "6. Use **“More details”** inside a card to see extra metadata such as long title, "
    "object type, materials, techniques and production place.\n"
    "7. Use **“View details”** to open a larger image and a structured list of metadata, "
    "together with a dedicated space for your **research notes**.\n"
    "8. Cards that already have notes display a small 📝 indicator so you can quickly "
    "spot annotated artworks.\n"
    "9. At any time, you can click **“Clear my entire selection”** to start over with an "
    "empty collection (this will also reset comparison marks for those artworks)."
)

st.markdown("### 3. Comparing artworks")

st.write(
    "Comparison is done in **two steps**, using the *My selection* page and the "
    "**🖼️ Compare Artworks** page:\n\n"
    "1. On the **My selection** page, use the checkbox **“Mark for comparison”** on the "
    "artworks you want to compare. You can mark **up to 4** candidates.\n"
    "2. Marked artworks get a subtle highlight and appear in the panel "
    "**“Comparison candidates (from My Selection)”**, where you can:\n"
    "   - see a list of all candidates,\n"
    "   - temporarily focus the gallery only on these artworks,\n"
    "   - clear all comparison marks at once.\n"
    "3. Open the **🖼️ Compare Artworks** page from the sidebar.\n"
    "4. You will see the same comparison candidates at the top, each with a thumbnail, "
    "title, artist, date (when available) and object ID.\n"
    "5. Under each candidate, use **“Include in comparison pair”** to select which ones "
    "will be part of the current A/B pair (the selected ones get a stronger glow).\n"
    "6. Choose **exactly two** artworks. The app will then show a **side-by-side comparison** "
    "section, including images, titles, artists, dates, object IDs and links to the "
    "official Rijksmuseum pages.\n"
    "7. Use the buttons in the controls panel to **clear only the current pair** or "
    "**clear all comparison marks in My selection** and start again."
)

st.markdown("### 4. Exporting, sharing and notes")

st.write(
    "On the **My selection** page you will also find tools to export or share your work:\n\n"
    "- **Download selection as CSV** – for Excel, Google Sheets or other data tools. "
    "The CSV includes extra columns such as a `has_notes` flag and a `note_excerpt` "
    "(short preview of your note) so you can quickly filter annotated artworks.\n"
    "- **Download selection as JSON** – structured format that can be reused by scripts or apps.\n"
    "- **Download selection as PDF** – an illustrated report, one artwork per page, including "
    "basic metadata and, when enabled, your research notes and optional comments.\n"
    "- **Export research notes** – download your notes separately as CSV or JSON to combine "
    "with other research materials.\n"
    "- **Share / import a collection code** – generate a base64 text code that represents "
    "your current selection. Another person using the same app can paste this code to load "
    "exactly the same set of artworks."
)

st.markdown("### 5. PDF options")

st.write(
    "The PDF export offers a few additional options:\n\n"
    "- You can choose to generate a PDF with **all artworks in your current selection** "
    "or **only artworks that have notes**. The second option is useful when you selected "
    "many items but decided to annotate only a subset.\n"
    "- A separate **PDF setup** page (when enabled in the sidebar) lets you configure:\n"
    "   - whether to include a cover page,\n"
    "   - an opening text or introduction,\n"
    "   - whether to include research notes and additional comments.\n"
    "- PDF settings are stored locally so you do not need to reconfigure them every time."
)

st.caption(
    "Note: the PDF is always generated from the **current state of your selection** as "
    "loaded on the *My selection* page. If you recently added or removed artworks and the "
    "page count looks inconsistent, try reloading the page or toggling one artwork in your "
    "selection before clicking **Prepare PDF** again."
)

st.markdown("---")
st.markdown("## 💡 Tips")

st.write(
    "- If you do not want previous selections to appear pre-selected in new searches, "
    "remember to **clear your selection** on the *My selection* page.\n"
    "- When you need very high resolution or advanced zoom, use the links "
    "**“View on Rijksmuseum website”** or **“Open on Rijksmuseum website for full zoom”** "
    "in the detail view.\n"
    "- Use research notes to register hypotheses, references, classroom ideas or keywords "
    "you want to revisit later.\n"
    "- The `has_notes` and `note_excerpt` fields in the CSV make it easy to focus your "
    "analysis on artworks you actually commented.\n"
    "- You can combine this app with your own spreadsheets, notebooks or slide decks to "
    "build small research projects, classroom activities or exhibition studies."
)

st.markdown(
    "If you have ideas for new features or improvements, this prototype can be extended with "
    "more filters, richer PDF layouts, simple analytics dashboards or even AI-based tools "
    "to help summarise artworks and artists."
)