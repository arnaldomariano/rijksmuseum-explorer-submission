# Rijksmuseum Explorer — Research Prototype

A local-first research app built with Streamlit to explore artworks from the Rijksmuseum collection using **Rijksmuseum Data Services** (Search API + Linked Art / Linked Data).

> This is an independent prototype for study and research.  
> It is **not** an official Rijksmuseum product.

---

## ✨ Main features

### Explorer (Home)
- Search artworks via Rijksmuseum Data Services (Search API).
- Results dereferenced via the Linked Art resolver (JSON-LD).
- Local post-filters: authorship scope, year range, materials, production place.
- Local pagination over the fetched result set (no remote paging yet).
- Artwork cards with thumbnails, basic metadata and link to the museum website.
- Global selection: **“In my selection”** checkbox persisted on disk.

### My Selection
- Local favorites stored in `favorites.json`.
- Research notes stored in `notes.json` (one note per artwork).
- Internal filters (text, year range, artist, object type).
- “With / without notes” filters and notes keyword filter.
- Mark up to **4 artworks** as comparison candidates.
- Export tools:
  - Selection as **CSV** / **JSON**.
  - Research notes as **CSV** / **JSON**.
  - Share code with list of `objectNumbers`.
  - Optional illustrated **PDF** report (per-artwork pages).

### Compare Artworks
- Side-by-side comparison for 2–4 artworks marked as comparison candidates.
- Shows images, basic metadata and object IDs for fast visual analysis.

### Statistics
- High-level overview of usage (searches, selections, exports) based on a local CSV log.
- No personal or remote analytics — everything is stored locally.

### PDF Setup
- Control panel for the PDF export profile:
  - Include/exclude cover page.
  - Include/exclude opening text.
  - Include/exclude selection overview.
  - Include/exclude Rijksmuseum “About” text (when available).
  - Include/exclude notes.

### About
- Explains the goals, data sources and privacy / storage model of the app.

---

## 🧱 Tech stack

- **Python 3.10+**
- **Streamlit**
- `requests`
- Optional (for PDF export):
  - `reportlab`

All Python dependencies required to run the app are listed in `requirements.txt`.

---

## 🗂 Local-first storage

The app keeps everything on the local filesystem:

- `favorites.json` — global selection of artworks.
- `notes.json` — research notes per artwork.
- `rijks_explorer_events_*.csv` — local usage log for the Statistics page.
- `pdf_meta.json` — options saved from the PDF Setup page.

When deployed on **Streamlit Cloud**, the filesystem may be ephemeral.  
Treat local files as temporary unless you add persistent storage or manual downloads.

---

## 🔍 Data sources & credits

This prototype uses the **Rijksmuseum Data Services**, including:

- **Search API** — to retrieve candidate items for a query.
- **Linked Art resolver** — to dereference each item and obtain Linked Art (JSON-LD).
- **IIIF image endpoints** — for public image URLs when available.

For full rights information, zoom and authoritative descriptions, always refer to the official Rijksmuseum website.

> All rights to artworks, descriptions and images remain with the Rijksmuseum and respective rights holders.

No classic API key is used; the prototype relies on the public Data Services endpoints.

---

## ⚙️ Configuration

The app does not require any private secrets or API keys to run.

Optional configuration (advanced):

- `.streamlit/config.toml` — can be used to tweak default Streamlit theme settings
  (the app also injects its own dark theme CSS).

---

## 🚀 Running the app locally

1. **Clone the repository**

   ```bash
   git clone https://github.com/<your-user>/<your-repo>.git
   cd <your-repo>