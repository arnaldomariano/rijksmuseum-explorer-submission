"""
analytics.py — local-only analytics (no external tracking).

This module logs lightweight events:
- page views
- searches
- selection actions
- compare actions
- exports

Events are stored:
1) in st.session_state (always)
2) optionally appended to a local JSONL file (best effort)

On Streamlit Cloud, the filesystem may reset; session_state still works
within a session.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import streamlit as st

from app_paths import ANALYTICS_LOG_FILE


def _utc_now_iso() -> str:
    """ISO timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_state() -> None:
    """Initialize analytics state in session_state if missing."""
    st.session_state.setdefault("_analytics_events", [])
    st.session_state.setdefault("_analytics_once_keys", set())


def _append_to_file(event: Dict[str, Any]) -> None:
    """
    Best-effort append to JSONL.
    Never break the UI if write fails.
    """
    try:
        with open(ANALYTICS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # File logging is optional and may fail on some deployments.
        pass


def track_event(event: str, page: str, props: Optional[Dict[str, Any]] = None) -> None:
    """
    Record an analytics event locally.

    Parameters
    ----------
    event:
        Event name, e.g. "search_executed", "selection_add_item"
    page:
        Page identifier, e.g. "Explorer", "My_Selection"
    props:
        Optional dictionary with event-specific properties.
    """
    _ensure_state()

    payload = {
        "ts": _utc_now_iso(),
        "event": str(event),
        "page": str(page),
        "props": props or {},
    }

    # Always store in session_state
    st.session_state["_analytics_events"].append(payload)

    # Best-effort: append to JSONL
    _append_to_file(payload)


def track_event_once(
    event: str,
    page: str,
    once_key: str,
    props: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record an event only once per session (based on `once_key`).

    Example:
        track_event_once("page_view", "Explorer", "page_view::Explorer", {...})
    """
    _ensure_state()

    if once_key in st.session_state["_analytics_once_keys"]:
        return

    st.session_state["_analytics_once_keys"].add(once_key)
    track_event(event=event, page=page, props=props)