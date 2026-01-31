"""
app_paths.py — central paths for local persistence and assets.

This app uses local JSON files for:
- favorites (global selection)
- notes
- pdf metadata configuration
- analytics events (local only, no external tracking)

On Streamlit Cloud, the filesystem is ephemeral, so these files may reset
when the app restarts. For demo/submission, this is acceptable.
"""

from __future__ import annotations

from pathlib import Path

# Project root (folder where this file lives)
ROOT_DIR = Path(__file__).resolve().parent

# App folders
ASSETS_DIR = ROOT_DIR / "assets"
DATA_DIR = ROOT_DIR / "data"
ANALYTICS_DIR = DATA_DIR / "analytics"

# Ensure directories exist (safe no-op if already created)
DATA_DIR.mkdir(parents=True, exist_ok=True)
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

# Core files (local persistence)
FAV_FILE = DATA_DIR / "favorites.json"
NOTES_FILE = DATA_DIR / "notes.json"
PDF_META_FILE = DATA_DIR / "pdf_meta.json"

# Assets
HERO_IMAGE_PATH = ASSETS_DIR / "rijks_header.jpg"

# Analytics file (JSONL)
ANALYTICS_LOG_FILE = ANALYTICS_DIR / "events.jsonl"