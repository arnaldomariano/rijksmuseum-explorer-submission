# analytics.py
"""
Local analytics for Rijksmuseum Explorer.

This module provides a very simple, fully local analytics system that:
- stores events as JSON lines in `analytics_events.json`,
- uses Streamlit's session_state to keep a per-session `session_id`,
- optionally enriches events with installation metadata
  (city, country, timezone) from `analytics_config.json`,
- exposes two main functions:

    track_event(event, page, props=None)
    track_event_once(event, page, once_key, props=None)

No data is sent to any external server. Everything stays on disk
in the same folder as the app.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st

from app_paths import ANALYTICS_FILE, ANALYTICS_CONFIG_FILE


# ============================================================
# Paths and in-memory cache
# ============================================================
# NOTE:
# ANALYTICS_FILE and ANALYTICS_CONFIG_FILE are defined in app_paths.py.
# We keep a small in-memory cache so we do not re-read the config file
# on every event write.

_INSTALL_META_CACHE: Dict[str, Any] | None = None


# ============================================================
# Session identifier helpers
# ============================================================
def _get_session_id() -> str:
    """
    Return a stable session_id for the current Streamlit session.

    A random UUID is generated the first time and stored in
    st.session_state, so all events from the same browser session
    can be grouped together later.
    """
    key = "_analytics_session_id"
    sid = st.session_state.get(key)
    if not sid:
        sid = str(uuid.uuid4())
        st.session_state[key] = sid
    return sid


# ============================================================
# Installation metadata (optional, local only)
# ============================================================
def _load_installation_metadata() -> Dict[str, Any]:
    """
    Read installation metadata (city/country/timezone) from a local JSON file.

    The file path is defined by ANALYTICS_CONFIG_FILE and typically looks like:

        analytics_config.json

    Example expected keys (all optional):
        - installation_city
        - installation_country
        - installation_timezone

    The result is cached in memory and attached to every analytics event
    as props: "install_city", "install_country", "install_timezone".
    """
    cache_key = "_analytics_installation_meta"

    # Return cached metadata if already loaded in this Streamlit session
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    meta: Dict[str, Any] = {}
    try:
        if ANALYTICS_CONFIG_FILE.exists():
            with ANALYTICS_CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                meta = {
                    "install_city": data.get("installation_city"),
                    "install_country": data.get("installation_country"),
                    "install_timezone": data.get("installation_timezone"),
                }
    except Exception:
        # Analytics should never break the app; fallback to empty metadata
        meta = {}

    st.session_state[cache_key] = meta
    return meta


# (Legacy helper kept for backward compatibility / future use)
#def _get_installation_metadata() -> Dict[str, Any]:
    """
    Legacy helper that reads installation metadata and caches it globally.

    Currently not used by the main functions, but kept for backwards
    compatibility in case external code imports it.
    """
    global _INSTALL_META_CACHE

    if _INSTALL_META_CACHE is not None:
        return _INSTALL_META_CACHE

    meta: Dict[str, Any] = {}
    try:
        if ANALYTICS_CONFIG_FILE.exists():
            with ANALYTICS_CONFIG_FILE.open("r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
                if isinstance(loaded, dict):
                    meta = loaded
    except Exception:
        meta = {}

    # Provide default values if not present
    meta.setdefault("installation_city", "Unknown")
    meta.setdefault("installation_country", "Unknown")
    meta.setdefault("installation_timezone", "UTC")

    _INSTALL_META_CACHE = meta
    return meta


# ============================================================
# Low-level writer (append JSON lines to file)
# ============================================================
def _write_event(record: Dict[str, Any]) -> None:
    """
    Append a single analytics event as a JSON line.

    If anything goes wrong (permissions, disk full, etc.), the function
    fails silently. Analytics must never break the main app.
    """
    try:
        ANALYTICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with ANALYTICS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        # Analytics should never crash the app
        pass


# ============================================================
# Public API: track_event and track_event_once
# ============================================================
def track_event(
    event: str,
    page: str,
    props: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log a generic analytics event.

    Parameters
    ----------
    event:
        Short string identifying the type of event
        (e.g. "search_executed", "selection_add_item").
    page:
        Logical page name where the event occurred
        (e.g. "Explorer", "My_Selection", "PDF_Setup").
    props:
        Optional dictionary with extra properties for the event.
        These are merged with installation metadata.

    All events are stored locally in `analytics_events.json` as JSON lines
    with fields: ts, event, page, session_id, props.
    """
    base_props = props.copy() if isinstance(props, dict) else {}

    # Attach installation metadata (city/country/timezone) if available
    base_props.update(_load_installation_metadata())

    record = {
        "ts": time.time(),
        "event": event,
        "page": page,
        "session_id": _get_session_id(),
        "props": base_props,
    }
    _write_event(record)


def track_event_once(
    event: str,
    page: str,
    once_key: str,
    props: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log an event only once per Streamlit session, based on `once_key`.

    This is useful for events like page views, where we only want to register
    a single event per page and session, even if the user triggers reruns
    multiple times.

    Parameters
    ----------
    event:
        Event type (e.g. "page_view").
    page:
        Logical page name (e.g. "Explorer").
    once_key:
        Unique key used to remember if the event has already been logged
        during this session (e.g. "page_view::Explorer").
    props:
        Optional dictionary with extra properties.
    """
    state_key = f"_analytics_once::{once_key}"
    if st.session_state.get(state_key):
        # Already logged in this session; do nothing
        return

    # Mark as logged and forward to track_event
    st.session_state[state_key] = True
    track_event(event=event, page=page, props=props)