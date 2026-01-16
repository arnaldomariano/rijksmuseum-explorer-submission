# app_paths.py
"""
Centralized filesystem paths for the Rijksmuseum Explorer app.

All other modules should import paths from here instead of using
hard-coded strings, so the folder structure can be changed in a
single place if needed.
"""

from pathlib import Path

# ============================================================
# Base folders
# ============================================================
# BASE_DIR → project root (folder that contains this file)
BASE_DIR = Path(__file__).resolve().parent

# DATA_DIR currently points to "<project_root>/data/analytics"
# This keeps compatibility with the JSON files you have already generated.
DATA_DIR = BASE_DIR / "data" / "analytics"

# For clarity, analytics data lives in the same DATA_DIR
ANALYTICS_DIR = DATA_DIR

# Static assets (images, etc.)
ASSETS_DIR = BASE_DIR / "assets"

# Ensure base directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Local persistence files (selection, notes, PDF metadata)
# ============================================================
FAV_FILE = DATA_DIR / "favorites.json"
NOTES_FILE = DATA_DIR / "notes.json"
PDF_META_FILE = DATA_DIR / "pdf_meta.json"
LOCAL_COLLECTION_FILE = BASE_DIR / "local_collection.json"
# ============================================================
# Analytics (local, anonymous)
# ============================================================
# Main events file (JSON Lines style, one event per line)
ANALYTICS_EVENTS_FILE = DATA_DIR / "analytics_events.json"

# Alias used by analytics.py (kept for backwards compatibility)
ANALYTICS_FILE = ANALYTICS_EVENTS_FILE

# Optional local configuration for analytics:
# - installation_city / installation_country / installation_timezone
# - analytics_admin_code (for the Statistics page access)
ANALYTICS_CONFIG_FILE = DATA_DIR / "analytics_config.json"

# ============================================================
# Assets
# ============================================================
HERO_IMAGE_PATH = ASSETS_DIR / "rijks_header.jpg"