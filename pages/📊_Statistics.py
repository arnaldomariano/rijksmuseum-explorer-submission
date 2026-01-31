"""
Statistics — local-only analytics dashboard.

Shows:
- session analytics events (always available)
- optional file-based analytics (if JSONL exists)
- most viewed artworks (based on "artwork_view" events)
- basic usage counters (searches, exports, comparisons)

No external tracking. This is strictly local.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Dict, List

import streamlit as st

from app_paths import ANALYTICS_LOG_FILE, FAV_FILE
from analytics import track_event_once


st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")

# Page view (once)
track_event_once(
    event="page_view",
    page="Statistics",
    once_key="page_view::Statistics",
    props={},
)

st.markdown("## 📊 Statistics")
st.caption("Local-only analytics. No data is sent externally.")


# ============================================================
# Helpers
# ============================================================
def _read_jsonl(path) -> List[Dict[str, Any]]:
    """Best-effort read of JSONL analytics file."""
    events: List[Dict[str, Any]] = []
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
    except Exception:
        return []
    return events


def _load_favorites_count() -> int:
    try:
        if FAV_FILE.exists():
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return len(data)
    except Exception:
        pass
    return 0


# ============================================================
# Load events
# ============================================================
session_events = st.session_state.get("_analytics_events", [])
file_events = _read_jsonl(ANALYTICS_LOG_FILE)

st.markdown("### Event sources")
col_a, col_b = st.columns(2)
with col_a:
    st.metric("Session events", value=len(session_events))
with col_b:
    st.metric("File events (JSONL)", value=len(file_events))

st.metric("Saved artworks (favorites.json)", value=_load_favorites_count())


# ============================================================
# Aggregate (prefer session events for “live” view)
# ============================================================
events = session_events if session_events else file_events

if not events:
    st.info("No analytics events recorded yet. Use the app and come back here.")
    st.stop()

event_counts = Counter(e.get("event") for e in events if isinstance(e, dict))
page_counts = Counter(e.get("page") for e in events if isinstance(e, dict))

st.markdown("### Usage counters")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Searches", event_counts.get("search_executed", 0))
col2.metric("Artwork views", event_counts.get("artwork_view", 0))
col3.metric("Comparisons", event_counts.get("compare_clicked", 0))
col4.metric("Exports", event_counts.get("export_download", 0) + event_counts.get("export_prepare", 0))

st.markdown("### Top pages")
for page, cnt in page_counts.most_common(10):
    st.write(f"- **{page}**: {cnt}")


# ============================================================
# Top viewed artworks
# ============================================================
views = defaultdict(int)
artists = defaultdict(str)

for e in events:
    if not isinstance(e, dict):
        continue
    if e.get("event") != "artwork_view":
        continue
    props = e.get("props") or {}
    obj_id = props.get("object_id")
    if isinstance(obj_id, str) and obj_id.strip():
        views[obj_id] += 1
        a = props.get("artist")
        if isinstance(a, str) and a.strip():
            artists[obj_id] = a.strip()

top_views = sorted(views.items(), key=lambda x: x[1], reverse=True)[:15]

st.markdown("### Most viewed artworks")
if not top_views:
    st.caption("No artwork_view events recorded yet.")
else:
    for obj_id, cnt in top_views:
        artist = artists.get(obj_id, "Unknown artist")
        st.write(f"- `{obj_id}` — **{artist}** — {cnt} view(s)")