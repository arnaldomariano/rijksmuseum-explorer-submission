# pages/📊_Statistics.py
"""
Statistics dashboard for Rijksmuseum Explorer.

This Streamlit page reads anonymous, fully local analytics events from
`analytics_events.json` and presents them in a way that is useful for
museum staff.

Key features
------------
- Optional admin access gate:
  - If an access code is configured in `analytics_config.json`, only
    users who provide the correct code can see this page.
  - If no code is configured, the page is fully visible (development mode).

- Basic metrics:
  - Total events, number of event types, time window.

- Filters:
  - Filter data by event type using a multiselect widget.

- Exports:
  - Download filtered raw events as CSV.
  - Download aggregated statistics as CSV (event types, page views,
    exports, artworks, artists, search queries, search configs).

- Maintenance:
  - Clear the local analytics file from the UI (no data is sent anywhere).

- Grouped panels:
  - Search activity, selection activity, views & navigation, exports,
    top artworks, top artists, page views and search queries.
"""

import json
import io
import csv
from collections import Counter
from datetime import datetime
from typing import Optional

import streamlit as st

from app_paths import ANALYTICS_EVENTS_FILE, ANALYTICS_CONFIG_FILE


# ============================================================
# Maintenance helpers (clear analytics file)
# ============================================================
def clear_analytics_events() -> bool:
    """
    Reset the analytics events file to an empty file.

    Returns
    -------
    bool
        True if the file was successfully cleared, False otherwise.
    """
    try:
        p = ANALYTICS_EVENTS_FILE
        p.parent.mkdir(parents=True, exist_ok=True)

        # overwrite file with empty content
        with open(p, "w", encoding="utf-8") as f:
            f.write("")

        return True
    except Exception:
        return False


# ============================================================
# Page config and header
# ============================================================
st.set_page_config(page_title="Statistics", layout="wide")
st.markdown("## 📊 Usage statistics (local, anonymous)")

st.caption(
    "This dashboard reads the local file `analytics_events.json` created by the app. "
    "No data is sent anywhere."
)


# ============================================================
# Admin access gate (optional)
# ============================================================
def _get_admin_access_code() -> str:
    """
    Read an optional admin access code from analytics_config.json.

    If the key `analytics_admin_code` is present and non-empty, it is
    used to protect this page. If not present, an empty string is
    returned and the page is fully accessible (development mode).
    """
    try:
        if ANALYTICS_CONFIG_FILE.exists():
            with ANALYTICS_CONFIG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f) or {}
            if isinstance(data, dict):
                return (data.get("analytics_admin_code") or "").strip()
    except Exception:
        # Never break the app because of a config problem
        return ""
    return ""


def require_admin_access() -> None:
    """
    Simple access gate for the statistics page.

    Behavior:
    - If no admin code is configured in `analytics_config.json`, the page
      is fully visible and a small info message explains that.
    - If an admin code is configured:
        * the user must enter it in a password field;
        * after a successful validation, the flag
          `is_analytics_admin` is stored in session_state and the
          user does not need to re-enter the code during this session;
        * if the code is wrong (or empty), the page stops rendering.
    """
    admin_code = _get_admin_access_code()

    # If no code configured → full access (useful in dev)
    if not admin_code:
        st.info(
            "⚠️ Analytics admin access code is not configured. "
            "In this development environment, the statistics panel is fully visible."
        )
        return

    # Already validated in this session?
    if st.session_state.get("is_analytics_admin"):
        return

    st.warning(
        "This page is restricted to museum staff.\n\n"
        "Please enter the analytics access code to continue."
    )
    typed = st.text_input("Access code", type="password")

    if not typed:
        st.stop()

    if typed.strip() == admin_code:
        st.session_state["is_analytics_admin"] = True
        st.success("Access granted.")
        # 🔴 novo: faz um rerun imediato SEM mostrar mais o formulário
        st.rerun()
    else:
        st.error("Invalid access code.")
        st.stop()

# Enforce admin access before loading any data
require_admin_access()


# ============================================================
# Helpers: loading and exporting events
# ============================================================
@st.cache_data(show_spinner=False)
def load_events(path, version: float) -> list[dict]:
    """
    Load analytics events from the given file as a list of dicts.

    Parameters
    ----------
    path:
        Path to the analytics events file.
    version:
        File modification time (mtime). This is used only as a cache key
        so that Streamlit invalidates the cache when the file changes.

    Returns
    -------
    list[dict]
        List of parsed event records.
    """
    events: list[dict] = []
    if not path.exists():
        return events

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                # Skip malformed lines, but never break the page
                continue
    return events


def events_to_csv_bytes(events: list[dict]) -> bytes:
    """
    Convert a list of event dicts into CSV bytes.

    The function infers the union of all keys across events and generates
    a CSV where columns are:

        ["ts", "event", "page", "session_id", ...other keys...]

    Parameters
    ----------
    events:
        List of event records.

    Returns
    -------
    bytes
        CSV content encoded as UTF-8 bytes.
    """
    if not events:
        return b""

    keys = set()
    for e in events:
        if isinstance(e, dict):
            keys.update(e.keys())

    preferred = ["ts", "event", "page", "session_id"]
    columns = preferred + sorted([k for k in keys if k not in preferred])

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for e in events:
        writer.writerow(e)

    return buffer.getvalue().encode("utf-8")


# ============================================================
# Load events and show basic debug info
# ============================================================
p = ANALYTICS_EVENTS_FILE
version = p.stat().st_mtime if p.exists() else 0.0

events = load_events(ANALYTICS_EVENTS_FILE, version)

p = ANALYTICS_EVENTS_FILE
#st.caption(
#   f"DEBUG file: `{p}` | exists={p.exists()} | "
#   f"size={p.stat().st_size if p.exists() else '—'} bytes | "
#   f"mtime={datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S') if p.exists() else '—'}"
#)

if not events:
    st.info("No analytics events yet. Use the app normally and come back here.")
    st.stop()


# ============================================================
# Basic metrics
# ============================================================
total = len(events)
event_types = Counter(e.get("event") for e in events if e.get("event"))

ts_values = [e.get("ts") for e in events if isinstance(e.get("ts"), (int, float))]
min_ts = min(ts_values) if ts_values else None
max_ts = max(ts_values) if ts_values else None

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total events", total)
col2.metric("Event types", len(event_types))


def parse_ts(e: dict) -> Optional[datetime]:
    """
    Parse the 'ts' field of an event into a datetime object.

    Supports:
    - numeric timestamps (Unix seconds),
    - ISO 8601 strings (with or without 'Z' timezone suffix).
    """
    ts = e.get("ts")
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    if isinstance(ts, str):
        try:
            # handles "2025-12-13T..." (with or without timezone)
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


dt_values = [parse_ts(e) for e in events]
dt_values = [d for d in dt_values if isinstance(d, datetime)]

dt_min = min(dt_values) if dt_values else None
dt_max = max(dt_values) if dt_values else None

if dt_min and dt_max:
    col3.metric("First event", dt_min.strftime("%Y-%m-%d %H:%M"))
    col4.metric("Last event", dt_max.strftime("%Y-%m-%d %H:%M"))
else:
    col3.metric("First event", "—")
    col4.metric("Last event", "—")

st.markdown("---")


# ============================================================
# Filters (by event type)
# ============================================================
all_types = sorted(event_types.keys())
selected_types = st.multiselect(
    "Filter by event type",
    options=all_types,
    default=all_types,
)

selected_set = set(selected_types)
filtered = [e for e in events if e.get("event") in selected_set]


# ============================================================
# Export filtered events (raw CSV)
# ============================================================
csv_bytes = events_to_csv_bytes(filtered)
filename = f"analytics_events_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

st.download_button(
    "📄 Download events (CSV)",
    data=csv_bytes,
    file_name=filename,
    mime="text/csv",
    key="dl_analytics_csv",
)


# ============================================================
# Aggregations (counters by different dimensions)
# ============================================================
counts_by_type = Counter(e.get("event") for e in filtered if e.get("event"))

page_views_by_page = Counter()
views_by_object = Counter()
views_by_artist = Counter()
exports_by_format = Counter()
search_queries = Counter()
search_configs = Counter()

for e in filtered:
    ev = e.get("event")
    page_name = e.get("page") or "(unknown page)"
    props = e.get("props") or {}

    # Page views
    if ev == "page_view":
        page_views_by_page[page_name] += 1

    # Artwork views / detail opens / selection as "view" signal
    if ev in ("artwork_detail_opened", "artwork_view", "selection_add_item"):
        obj = props.get("object_id")
        artist = props.get("artist")
        if obj:
            views_by_object[obj] += 1
        if artist:
            views_by_artist[artist] += 1

    # Exports
    if ev in ("export_download", "export_prepare"):
        fmt = (props.get("format") or "").lower().strip()
        if fmt:
            exports_by_format[fmt] += 1

    # Searches
    if ev == "search_executed":
        q = (props.get("query_sample") or "").strip()
        if q:
            search_queries[q] += 1

        cfg_key = (
            f"type={props.get('object_type', 'Any')}; "
            f"sort={props.get('sort_by', 'relevance')}; "
            f"year={props.get('year_min', '')}-{props.get('year_max', '')}; "
            f"material={bool(props.get('has_material_filter'))}; "
            f"place={bool(props.get('has_place_filter'))}"
        )
        search_configs[cfg_key] += 1


# ============================================================
# Export aggregated stats (CSV)
# ============================================================
stats_rows: list[dict] = []

# 1) Event counts by type
for ev_type, count in counts_by_type.most_common():
    stats_rows.append(
        {"category": "event_type", "key": ev_type or "(none)", "count": count}
    )

# 2) Page views by page
for page_name, count in page_views_by_page.most_common():
    stats_rows.append(
        {"category": "page_view", "key": page_name, "count": count}
    )

# 3) Exports by format
for fmt, count in exports_by_format.most_common():
    stats_rows.append(
        {"category": "export_format", "key": fmt or "(none)", "count": count}
    )

# 4) Artwork views by object ID
for obj, count in views_by_object.most_common():
    stats_rows.append(
        {"category": "object_id", "key": obj, "count": count}
    )

# 5) Artwork views by artist
for artist, count in views_by_artist.most_common():
    stats_rows.append(
        {"category": "artist", "key": artist, "count": count}
    )

# 6) Searches by query (query_sample)
for query, count in search_queries.most_common():
    stats_rows.append(
        {"category": "search_query", "key": query, "count": count}
    )

# 7) Searches by configuration (type, sort, local filters)
for cfg, count in search_configs.most_common():
    stats_rows.append(
        {"category": "search_config", "key": cfg, "count": count}
    )

if stats_rows:
    stats_buffer = io.StringIO()
    writer = csv.DictWriter(
        stats_buffer,
        fieldnames=["category", "key", "count"],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(stats_rows)
    stats_csv_bytes = stats_buffer.getvalue().encode("utf-8")

    st.download_button(
        "📊 Download aggregated stats (CSV)",
        data=stats_csv_bytes,
        file_name=f"analytics_stats_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
        key="dl_analytics_stats_csv",
    )
else:
    st.caption("No aggregated stats available yet for current filters.")

st.markdown("---")


# ============================================================
# Maintenance section (clear file)
# ============================================================
st.subheader("🧹 Maintenance")

if "confirm_clear_analytics" not in st.session_state:
    st.session_state["confirm_clear_analytics"] = False

col_a, col_b = st.columns([1, 2])

with col_a:
    if not st.session_state["confirm_clear_analytics"]:
        if st.button("Clear analytics data", key="btn_clear_analytics_step1"):
            st.session_state["confirm_clear_analytics"] = True
            st.rerun()
    else:
        if st.button("✅ Confirm clear", key="btn_clear_analytics_step2"):
            ok = clear_analytics_events()
            st.session_state["confirm_clear_analytics"] = False

            if ok:
                # 1) Clear global cache so the loader sees an empty file
                st.cache_data.clear()

                # 2) Remove any analytics-related flags from the session
                for k in list(st.session_state.keys()):
                    if k.startswith("analytics_") or k.startswith("_analytics_"):
                        del st.session_state[k]

                st.success("Analytics file cleared (and session analytics flags reset).")
            else:
                st.error("Could not clear analytics file.")

            st.rerun()

with col_b:
    if st.session_state["confirm_clear_analytics"]:
        st.warning(
            f"This will permanently clear your local analytics file:\n\n`{ANALYTICS_EVENTS_FILE}`\n\n"
            "Click **Confirm clear** to proceed."
        )
    else:
        st.caption("Clears the local file only. No data is sent anywhere.")

st.markdown("---")


# ============================================================
# Display panels (grouped view)
# ============================================================
cA, cB = st.columns([1, 1])

# Mapping from event types to human-readable groups
event_groups = {
    "Search activity": [
        "search_executed",
    ],
    "Selection activity": [
        "selection_add_item",
        "selection_remove_item",
        "selection_add_all",
        "selection_remove_all",
    ],
    "Views & navigation": [
        "page_view",
        "artwork_view",
        "artwork_detail_opened",
    ],
    "Exports": [
        "export_prepare",
        "export_download",
    ],
}

all_grouped_events = {e for group in event_groups.values() for e in group}

with cA:
    st.subheader("Events by type (grouped)")
    st.caption(
        "Overview of how the app is used: searches, selections, page views and exports. "
        "All numbers respect the current event-type filter above."
    )

    # Show main groups
    for group_label, ev_list in event_groups.items():
        group_total = sum(counts_by_type.get(ev, 0) for ev in ev_list)
        if group_total <= 0:
            continue

        st.markdown(f"**{group_label}**")
        for ev in ev_list:
            count = counts_by_type.get(ev, 0)
            if count > 0:
                st.write(f"- `{ev}`: {count}")

    # Any event not covered by the groups above
    other_events = {
        ev: c
        for ev, c in counts_by_type.items()
        if ev not in all_grouped_events
    }
    if other_events:
        st.markdown("**Other events**")
        for ev, c in other_events.items():
            st.write(f"- `{ev}`: {c}")

with cB:
    st.subheader("Exports by format")
    st.caption(
        "Number of exports prepared or downloaded from this installation "
        "(for example, CSV or PDF files)."
    )
    if exports_by_format:
        for k, v in exports_by_format.most_common():
            st.write(f"- **{k.upper()}**: {v}")
    else:
        st.write("No export events yet for the current filter.")

st.markdown("---")


# ============================================================
# Most viewed artworks / artists
# ============================================================
c1, c2 = st.columns(2)

with c1:
    st.subheader("Top artworks (views)")
    st.caption(
        "Counts how many times each artwork was marked in the selection or "
        "viewed in detail, according to the current filters."
    )
    top_n = st.slider("How many artworks to show", 5, 50, 15, key="top_artworks_n")
    if views_by_object:
        for obj, n in views_by_object.most_common(top_n):
            st.write(f"- **{obj}**: {n}")
    else:
        st.write("No artwork view events yet for the current filter.")

with c2:
    st.subheader("Top artists (views)")
    st.caption(
        "Artists ranked by the number of views of their artworks "
        "(based on selection and detail-view events, filtered above)."
    )
    top_n_a = st.slider("How many artists to show", 5, 50, 15, key="top_artists_n")
    if views_by_artist:
        for artist, n in views_by_artist.most_common(top_n_a):
            st.write(f"- **{artist}**: {n}")
    else:
        st.write("No artist view events yet for the current filter.")

st.markdown("---")


# ============================================================
# Page views & search queries
# ============================================================
c3, c4 = st.columns(2)

with c3:
    st.subheader("Page views by page")
    st.caption("Number of visits to each page of the app (Explorer, My Selection, etc.).")
    if page_views_by_page:
        for page_name, count in page_views_by_page.most_common():
            st.write(f"- **{page_name}**: {count}")
    else:
        st.write("No page view events yet for the current filter.")

with c4:
    st.subheader("Top search queries")
    st.caption("Most frequent search terms used in the Explorer page.")
    max_q = st.slider(
        "How many queries to show",
        5,
        50,
        10,
        key="top_queries_n",
    )
    if search_queries:
        for query, n in search_queries.most_common(max_q):
            label = query or "(empty search)"
            st.write(f"- **{label}**: {n}")
    else:
        st.write("No search events yet for the current filter.")

st.markdown("---")


# ============================================================
# Raw events (debug)
# ============================================================
with st.expander("🔎 Raw events (debug)", expanded=False):
    st.caption(
        "Last events recorded in the local analytics file. "
        "Useful for debugging or for exporting a small sample."
    )
    st.write(f"File: `{ANALYTICS_EVENTS_FILE}`")
    st.json(filtered[-50:])