"""
analytics.py — local-only analytics (no external tracking).

This module records lightweight usage events for the Rijksmuseum Explorer
prototype, such as:

- page views
- searches
- selection actions
- compare actions
- exports

Events are stored:

1) In `st.session_state["_analytics_events"]` for the current session.
2) Optionally appended to a local JSONL file on disk (`ANALYTICS_LOG_FILE`).

No data is sent to any external analytics service. This is intended only for
local debugging and for internal museum evaluation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import streamlit as st

from app_paths import ANALYTICS_LOG_FILE


def _utc_now_iso() -> str:
    """Return a UTC timestamp as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _ensure_state() -> None:
    """
    Ensure the analytics-related keys exist in Streamlit's session_state.

    - `_analytics_events`: list of recorded events for this session.
    - `_analytics_once_keys`: set of markers used by track_event_once.
    """
    st.session_state.setdefault("_analytics_events", [])
    st.session_state.setdefault("_analytics_once_keys", set())


def _append_to_file(event: Dict[str, Any]) -> None:
    """
    Best-effort append of a single event to the JSONL log file.

    If writing fails (for example, on ephemeral file systems),
    the exception is swallowed so the UI never breaks because of logging.
    """
    try:
        with open(ANALYTICS_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        # File logging is optional and may fail on some deployments.
        pass


def track_event(event: str, page: str, props: Optional[Dict[str, Any]] = None) -> None:
    """
    Record a single analytics event.

    Parameters
    ----------
    event:
        Short event name (e.g. "page_view", "search_executed").
    page:
        Logical page name where the event happened
        (e.g. "Explorer", "My_Selection", "Statistics").
    props:
        Optional dictionary with extra context, such as:
        - query text, filters, sort options
        - selected object IDs
        - export format, etc.
    """
    _ensure_state()

    # We use a single timestamp and store it under two keys:
    # - "timestamp": the name expected by the Statistics dashboard
    # - "ts": kept for backwards compatibility with older files
    now = _utc_now_iso()

    payload: Dict[str, Any] = {
        "timestamp": now,
        "ts": now,
        "event": str(event),
        "page": str(page),
        "props": props or {},
    }

    # 1) Keep it in memory for this session
    st.session_state["_analytics_events"].append(payload)

    # 2) Best-effort write to the JSONL file
    _append_to_file(payload)


def track_event_once(
    event: str,
    page: str,
    once_key: str,
    props: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record an event only once per session, identified by `once_key`.

    This is useful for events like "page_view" on admin/diagnostic pages,
    where we don't want to count multiple refreshes.

    Example
    -------
    track_event_once(
        event="page_view",
        page="Explorer",
        once_key="page_view::Explorer",
        props={"source": "main_app"},
    )
    """
    _ensure_state()

    if once_key in st.session_state["_analytics_once_keys"]:
        # Already recorded in this session; do nothing.
        return

    st.session_state["_analytics_once_keys"].add(once_key)
    track_event(event=event, page=page, props=props)