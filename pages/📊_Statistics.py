"""
Statistics — local-only analytics dashboard (admin-only).

This page is meant for museum staff / curators:

- Reads the local analytics JSONL file (no external tracking).
- Shows usage counters and top lists (searches, views, exports).
- Allows CSV export for further analysis (Power BI / Tableau / etc.).
- Access can be protected with a password via STATS_PASSWORD in secrets.toml.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Iterable

import streamlit as st

from app_paths import ANALYTICS_LOG_FILE, FAV_FILE
from analytics import track_event_once


# ============================================================
# Optional password gate (admin-only access)
# ============================================================
def require_stats_password() -> None:
    """
    Optional password gate for the statistics page.

    If STATS_PASSWORD is defined in .streamlit/secrets.toml,
    the user must enter the correct password to see the dashboard.

    If STATS_PASSWORD is missing or empty, the page is shown normally,
    but an info message is displayed (development mode).
    """
    try:
        admin_password = st.secrets.get("STATS_PASSWORD", "")
    except Exception:
        admin_password = ""

    if not admin_password:
        st.info(
            "Statistics are visible because no admin password is configured. "
            "To restrict access, set `STATS_PASSWORD` in `.streamlit/secrets.toml`."
        )
        return

    st.markdown("#### Admin access required")
    pwd = st.text_input("Enter statistics password", type="password")

    if not pwd:
        st.stop()

    if pwd != admin_password:
        st.error("Incorrect password.")
        st.stop()
    # correct password → continue rendering


# ============================================================
# Page config
# ============================================================
st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")

# Require password first
require_stats_password()

# Page view (once) – only after passing the gate
track_event_once(
    event="page_view",
    page="Statistics",
    once_key="page_view::Statistics",
    props={},
)

st.markdown("## 📊 Usage statistics (local, anonymous)")
st.caption(
    "This dashboard reads the local file `analytics_events.json` created by the app. "
    "No data is sent anywhere."
)


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
                        ev = json.loads(line)
                        if isinstance(ev, dict):
                            events.append(ev)
                    except Exception:
                        continue
    except Exception:
        return []
    return events


def _load_favorites_count() -> int:
    """Return how many artworks are currently in favorites.json."""
    try:
        if FAV_FILE.exists():
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return len(data)
    except Exception:
        pass
    return 0


def _parse_timestamp(ev: Dict[str, Any]) -> datetime | None:
    """Try to parse the event timestamp (ISO string) to datetime."""
    ts = ev.get("timestamp")
    if not isinstance(ts, str):
        return None
    # Try a couple of ISO-like formats
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.fromisoformat(ts.replace("Z", ""))
        except Exception:
            continue
    return None


def _flatten_events_to_csv(events: Iterable[Dict[str, Any]]) -> str:
    """
    Convert events list to CSV string.

    Columns:
        timestamp, event, page, props (JSON)
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "event", "page", "props_json"])

    for ev in events:
        if not isinstance(ev, dict):
            continue
        ts = ev.get("timestamp", "")
        event_name = ev.get("event", "")
        page = ev.get("page", "")
        props = ev.get("props", {})
        try:
            props_str = json.dumps(props, ensure_ascii=False)
        except Exception:
            props_str = "{}"
        writer.writerow([ts, event_name, page, props_str])

    return output.getvalue()


def _aggregated_stats_to_csv(
    event_counts: Counter,
    search_queries: Counter,
    top_artworks: List[tuple[str, int]],
    top_artists: List[tuple[str, int]],
) -> str:
    """
    Build a simple aggregated CSV with multiple sections.

    Sections are separated by blank lines.
    """
    out = io.StringIO()
    writer = csv.writer(out)

    # Section 1: events by type
    writer.writerow(["Section", "Key", "Value"])
    for evt, cnt in event_counts.most_common():
        writer.writerow(["event_type", evt, cnt])

    writer.writerow([])

    # Section 2: top search queries
    for q, cnt in search_queries.most_common(50):
        writer.writerow(["search_query", q, cnt])

    writer.writerow([])

    # Section 3: top artworks
    for obj_id, cnt in top_artworks:
        writer.writerow(["artwork", obj_id, cnt])

    writer.writerow([])

    # Section 4: top artists
    for artist, cnt in top_artists:
        writer.writerow(["artist", artist, cnt])

    return out.getvalue()


# ============================================================
# Load events (file + session)
# ============================================================
session_events = st.session_state.get("_analytics_events", [])
file_events = _read_jsonl(ANALYTICS_LOG_FILE)

# Debug / context about the analytics file
debug_str = (
    f"DEBUG file: `{ANALYTICS_LOG_FILE}` | "
    f"exists={ANALYTICS_LOG_FILE.exists()} "
)

if ANALYTICS_LOG_FILE.exists():
    try:
        stat = ANALYTICS_LOG_FILE.stat()
        debug_str += f"| size={stat.st_size} bytes | mtime={datetime.fromtimestamp(stat.st_mtime)}"
    except Exception:
        pass

st.caption(debug_str)

# Decide which events we use as the main source
if file_events:
    events = file_events
    source_label = "file (persistent)"
else:
    events = session_events
    source_label = "session (current run only)"

if not events:
    st.info("No analytics events recorded yet. Use the app and come back here.")
    st.stop()

# Basic high-level metrics
all_event_names = [e.get("event") for e in events if isinstance(e, dict)]
event_counts = Counter(all_event_names)

timestamps = [_parse_timestamp(e) for e in events]
timestamps = [t for t in timestamps if t is not None]
first_event = min(timestamps) if timestamps else None
last_event = max(timestamps) if timestamps else None

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Total events", value=len(events))
col_b.metric("Event types", value=len(event_counts))
col_c.metric("Source", value=source_label)
col_d.metric("Saved artworks (favorites.json)", value=_load_favorites_count())

col_e, col_f = st.columns(2)
col_e.metric("First event", value=str(first_event) if first_event else "—")
col_f.metric("Last event", value=str(last_event) if last_event else "—")


# ============================================================
# Event type filter
# ============================================================
unique_events = sorted(event_counts.keys())
st.markdown("### Filter by event type")
selected_types = st.multiselect(
    "Select which event types to include",
    options=unique_events,
    default=unique_events,
)

if selected_types:
    filtered_events = [
        e for e in events
        if isinstance(e, dict) and e.get("event") in selected_types
    ]
else:
    filtered_events = events

if not filtered_events:
    st.warning("No events after applying this filter.")
    st.stop()

filtered_counts = Counter(
    e.get("event") for e in filtered_events if isinstance(e, dict)
)


# ============================================================
# Download buttons (events & aggregated)
# ============================================================
st.markdown("### Export analytics")

events_csv = _flatten_events_to_csv(filtered_events)

# Aggregated stats will be filled after we compute them, but we can
# declare the variable here to keep the structure clear.
aggregated_csv: str | None = None

col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button(
        "📄 Download events (CSV)",
        data=events_csv,
        file_name="rijks_explorer_events.csv",
        mime="text/csv",
        use_container_width=True,
    )
# aggregated_csv will be set after computing aggregates; download button is below


# ============================================================
# Aggregated views
# ============================================================
st.markdown("### Events by type")
for evt, cnt in filtered_counts.most_common():
    st.write(f"- **{evt}**: {cnt}")

# --- Exports by format ---
st.markdown("### Exports by format")
exports_by_format = Counter()
for e in filtered_events:
    if not isinstance(e, dict):
        continue
    if e.get("event") not in ("export_download", "export_prepare"):
        continue
    props = e.get("props") or {}
    fmt = props.get("format") or "unknown"
    exports_by_format[str(fmt)] += 1

if not exports_by_format:
    st.caption("No export events recorded yet.")
else:
    for fmt, cnt in exports_by_format.most_common():
        st.write(f"- **{fmt}**: {cnt}")

# --- Page views by page ---
st.markdown("### Page views by page")
page_views = Counter()
for e in filtered_events:
    if not isinstance(e, dict):
        continue
    if e.get("event") != "page_view":
        continue
    page_name = e.get("page") or "unknown"
    page_views[str(page_name)] += 1

if not page_views:
    st.caption("No page_view events recorded yet.")
else:
    for page, cnt in page_views.most_common():
        st.write(f"- **{page}**: {cnt}")

# --- Top search queries ---
st.markdown("### Top search queries")

search_queries = Counter()
for e in filtered_events:
    if not isinstance(e, dict):
        continue
    if e.get("event") != "search_executed":
        continue
    props = e.get("props") or {}
    q = props.get("query_sample") or props.get("query") or ""
    if not isinstance(q, str):
        continue
    q = q.strip()
    if not q:
        continue
    search_queries[q] += 1

max_queries = st.slider("How many queries to show", min_value=5, max_value=50, value=10)
if not search_queries:
    st.caption("No search_executed events recorded yet.")
else:
    for q, cnt in search_queries.most_common(max_queries):
        st.write(f"- **{q}**: {cnt}")


# --- Top artworks (views) ---
st.markdown("### Top artworks (views)")

views_by_object = defaultdict(int)
artist_by_object = defaultdict(str)

for e in filtered_events:
    if not isinstance(e, dict):
        continue
    if e.get("event") != "artwork_view":
        continue
    props = e.get("props") or {}
    obj_id = props.get("object_id")
    artist = props.get("artist")
    if isinstance(obj_id, str) and obj_id.strip():
        views_by_object[obj_id] += 1
        if isinstance(artist, str) and artist.strip():
            artist_by_object[obj_id] = artist.strip()

max_artworks = st.slider("How many artworks to show", min_value=5, max_value=50, value=15)
top_artworks_list = sorted(
    views_by_object.items(), key=lambda x: x[1], reverse=True
)[:max_artworks]

if not top_artworks_list:
    st.caption("No artwork_view events recorded yet.")
else:
    for obj_id, cnt in top_artworks_list:
        artist = artist_by_object.get(obj_id, "Unknown artist")
        st.write(f"- `{obj_id}` — **{artist}**: {cnt} view(s)")


# --- Top artists (views) ---
st.markdown("### Top artists (views)")

views_by_artist = Counter()
for obj_id, cnt in views_by_object.items():
    artist = artist_by_object.get(obj_id, "Unknown artist")
    views_by_artist[artist] += cnt

max_artists = st.slider("How many artists to show", min_value=5, max_value=50, value=15)
top_artists_list = views_by_artist.most_common(max_artists)

if not top_artists_list:
    st.caption("No artwork_view events recorded yet.")
else:
    for artist, cnt in top_artists_list:
        st.write(f"- **{artist}**: {cnt} view(s)")

# Now that we have all aggregates, build the aggregated CSV
aggregated_csv = _aggregated_stats_to_csv(
    filtered_counts,
    search_queries,
    top_artworks_list,
    top_artists_list,
)

with col_dl2:
    st.download_button(
        "📊 Download aggregated stats (CSV)",
        data=aggregated_csv,
        file_name="rijks_explorer_aggregated_stats.csv",
        mime="text/csv",
        use_container_width=True,
    )


# ============================================================
# Maintenance: clear analytics
# ============================================================
st.markdown("### 🧹 Maintenance")

st.caption(
    "This will clear the local analytics file only. "
    "No external data is affected."
)

if st.button("Clear analytics data", type="secondary"):
    # Remove file + clear in-memory events
    try:
        if ANALYTICS_LOG_FILE.exists():
            ANALYTICS_LOG_FILE.unlink()
    except Exception as e:
        st.error(f"Could not delete analytics file: {e}")
    st.session_state.pop("_analytics_events", None)
    st.success("Analytics data cleared. New events will be recorded from now on.")