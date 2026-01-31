"""
rijks_api.py — Rijksmuseum Data Services adapter (Linked Art)

This module provides a stable "legacy-like" interface for the Streamlit UI:

- search_artworks(query, object_type, sort, page_size, page) -> (items, total)
- extract_year(dating_dict) -> int | None
- get_best_image_url(artwork_dict) -> str | None
- fetch_metadata_by_objectnumber(object_number) -> raw Linked Art JSON (DEV tools)

Data sources:
- Search API: https://data.rijksmuseum.nl/search/collection
- Resolver: dereference each PID via query-string content negotiation (_profile=la)

Notes:
- No classic API key is used.
- Pagination is local (we fetch up to N items, then slice locally).
- Authorship scope is supported through a research tag: `_attribution`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests


# ============================================================
# Constants
# ============================================================

SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"

SEARCH_TIMEOUT = 20
DETAIL_TIMEOUT = 20

# Upper bound safety (each PID requires a resolver request)
MAX_RESULTS_PER_SEARCH = 120


# ============================================================
# Errors
# ============================================================

class RijksAPIError(RuntimeError):
    """Raised when Rijksmuseum Data Services fails or returns unexpected data."""


# ============================================================
# Search params
# ============================================================

@dataclass
class SearchParams:
    query: str
    object_type: Optional[str]
    sort: str
    page_size: int
    page: int


# ============================================================
# HTTP session
# ============================================================

def _get_session() -> requests.Session:
    """Configured HTTP session."""
    s = requests.Session()
    s.headers.update({"User-Agent": "RijksmuseumExplorer/1.0"})
    return s


# ============================================================
# Search helpers
# ============================================================

def _search_ids(session: requests.Session, query: str, limit: int) -> List[str]:
    """
    Merge results from multiple query fields and dedupe by PID.

    This is intentionally conservative and predictable for a demo:
    - We do not implement remote paging (pageToken) yet.
    - We fetch up to `limit` PIDs, then resolve them.
    """
    fields = ("creator", "title", "description")

    seen: set[str] = set()
    ids: List[str] = []

    for field in fields:
        resp = session.get(SEARCH_URL, params={field: query}, timeout=SEARCH_TIMEOUT)
        if not resp.ok:
            raise RijksAPIError(f"Search API error ({resp.status_code}) via {field}: {resp.text[:200]}")

        data = resp.json()
        items = data.get("orderedItems") or data.get("items") or []

        for item in items:
            pid = item.get("id")
            if isinstance(pid, str) and pid.strip() and pid not in seen:
                seen.add(pid)
                ids.append(pid)
                if len(ids) >= limit:
                    return ids

    return ids


def _fetch_linked_art_json(session: requests.Session, pid_url: str) -> Dict[str, Any]:
    """Dereference a PID URL into Linked Art JSON-LD."""
    url = f"{pid_url.split('?')[0]}?_profile=la&_mediatype=application/ld+json"
    resp = session.get(url, timeout=DETAIL_TIMEOUT)

    if not resp.ok:
        raise RijksAPIError(f"Resolver error for {url} ({resp.status_code}): {resp.text[:200]}")

    try:
        obj = resp.json()
        return obj if isinstance(obj, dict) else {}
    except Exception as exc:
        raise RijksAPIError(f"Resolver returned non-JSON for {url}: {resp.text[:200]}") from exc


# ============================================================
# Linked Art utilities (web link, IIIF)
# ============================================================

def _extract_access_point_url(raw: Dict[str, Any]) -> Optional[str]:
    """
    Find the first access_point.id anywhere in the Linked Art JSON (recursive).
    Usually points to the public Rijksmuseum object page.
    """
    def walk(obj: Any) -> Optional[str]:
        if isinstance(obj, dict):
            ap = obj.get("access_point")
            if isinstance(ap, list) and ap:
                first = ap[0]
                if isinstance(first, dict):
                    u = first.get("id")
                    if isinstance(u, str) and u.strip():
                        return u.strip()

            for v in obj.values():
                hit = walk(v)
                if hit:
                    return hit

        elif isinstance(obj, list):
            for it in obj:
                hit = walk(it)
                if hit:
                    return hit

        return None

    return walk(raw)


def _clean_object_page_url(url: str) -> str:
    """Remove trailing --hash from object page URLs."""
    return re.sub(r"--[a-f0-9]{10,}$", "", url)


def _extract_object_number_from_access_point(url: str) -> Optional[str]:
    """Extract SK-... from the object page URL."""
    m = re.search(r"/object/(SK-[A-Z0-9-]+?)(?:--|/|$)", url)
    return m.group(1) if m else None


def _normalize_iiif_image_url(url: str, width: int = 900) -> str:
    """Normalize IIIF URLs to /full/<width>,/0/default.jpg"""
    u = url.strip()
    if u.endswith("/info.json"):
        base = u[:-len("/info.json")]
        return f"{base}/full/{width},/0/default.jpg"
    if "/full/" in u:
        base = u.split("/full/")[0]
        return f"{base}/full/{width},/0/default.jpg"
    return f"{u.rstrip('/')}/full/{width},/0/default.jpg"


def _extract_iiif_from_html(html: str) -> Optional[str]:
    """Extract an IIIF URL from object HTML (info.json preferred)."""
    m = re.search(r'https?://[^"\']*iiif[^"\']*/info\.json', html, flags=re.I)
    if m:
        return m.group(0)
    m = re.search(r'https?://[^"\']*iiif[^"\']*/full/[^"\']+', html, flags=re.I)
    if m:
        return m.group(0)
    return None


def _linked_art_image_url(raw: Dict[str, Any]) -> Optional[str]:
    """
    Best-effort image extraction without API key.

    1) Try embedded IIIF info.json anywhere in raw JSON
    2) Fallback: fetch access_point HTML and extract IIIF URL
    """
    raw_text = json.dumps(raw, ensure_ascii=False)
    m = re.search(r'https?://[^"\']*iiif[^"\']*/info\.json', raw_text, flags=re.I)
    if m:
        return _normalize_iiif_image_url(m.group(0), width=900)

    access_url = _extract_access_point_url(raw)
    if not access_url:
        return None

    try:
        resp = requests.get(access_url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if not resp.ok or not isinstance(resp.text, str):
            return None

        iiif = _extract_iiif_from_html(resp.text)
        if not iiif:
            return None

        return _normalize_iiif_image_url(iiif, width=900)
    except Exception:
        return None


# ============================================================
# Authorship classification (research tag)
# ============================================================

def _collect_attribution_texts(raw: Dict[str, Any]) -> List[str]:
    """Collect attribution-related short texts from produced_by.*.referred_to_by."""
    texts: List[str] = []
    produced_by = raw.get("produced_by")
    if not isinstance(produced_by, dict):
        return texts

    def pull(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        for item in (obj.get("referred_to_by") or []):
            if isinstance(item, dict):
                c = item.get("content")
                if isinstance(c, str) and c.strip():
                    texts.append(c.strip())

    pull(produced_by)

    parts = produced_by.get("part") or []
    if isinstance(parts, list):
        for p in parts:
            pull(p)

    return texts


def _classify_attribution(raw: Dict[str, Any], artist_name: str) -> str:
    """
    Returns:
      - direct / attributed / workshop / circle / after / unknown
    """
    if not artist_name or artist_name == "Unknown artist":
        return "unknown"

    name = artist_name.lower()
    texts = " | ".join(_collect_attribution_texts(raw)).lower()

    if not texts or name not in texts:
        return "unknown"

    if any(w in texts for w in ["attributed to", "toegeschreven aan", "zugeschrieben", "attribué à"]):
        return "attributed"
    if any(w in texts for w in ["workshop of", "atelier van", "werkplaats", "atelier de"]):
        return "workshop"
    if any(w in texts for w in ["circle of", "kring van", "school of", "navolger", "follower of", "cercle de"]):
        return "circle"
    if any(w in texts for w in ["after ", "naar ", "nach ", "d'après", "copy after", "kopie naar"]):
        return "after"

    if any(w in texts for w in ["painter:", "schilder:", "artist:", "gemaakt door", "door "]):
        return "direct"

    return "attributed"


# ============================================================
# Mapping: Linked Art -> UI dict
# ============================================================

def _map_linked_art_to_legacy_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Linked Art JSON into the stable dict shape expected by the UI."""
    access_url = _extract_access_point_url(raw)

    # objectNumber: prefer SK-... if possible
    object_number = "unknown-id"
    if access_url:
        sk = _extract_object_number_from_access_point(access_url)
        if sk:
            object_number = sk

    if object_number == "unknown-id":
        object_number = raw.get("id") or raw.get("@id") or "unknown-id"

    links: Dict[str, str] = {}
    if access_url:
        links["web"] = _clean_object_page_url(access_url)

    # Title
    title = "Untitled"
    identified_by = raw.get("identified_by") or []
    if isinstance(identified_by, list):
        for ident in identified_by:
            if isinstance(ident, dict):
                c = ident.get("content")
                if isinstance(c, str) and c.strip():
                    title = c.strip()
                    break

    # Artist
    principal = "Unknown artist"
    produced_by = raw.get("produced_by")
    if isinstance(produced_by, dict):
        rtb = produced_by.get("referred_to_by") or []
        if isinstance(rtb, list):
            for item in rtb:
                if isinstance(item, dict):
                    c = item.get("content")
                    if isinstance(c, str) and c.strip():
                        principal = c.strip()
                        break

        if principal == "Unknown artist":
            parts = produced_by.get("part") or []
            if isinstance(parts, list) and parts:
                p0 = parts[0] if isinstance(parts[0], dict) else None
                if isinstance(p0, dict):
                    rtb2 = p0.get("referred_to_by") or []
                    if isinstance(rtb2, list):
                        for item in rtb2:
                            if isinstance(item, dict):
                                c = item.get("content")
                                if isinstance(c, str) and c.strip():
                                    principal = c.split(":", 1)[-1].strip() or c.strip()
                                    break

    # Dating
    dating: Dict[str, Any] = {}
    year: Optional[int] = None
    presenting_date: Optional[str] = None

    if isinstance(produced_by, dict):
        timespan = produced_by.get("timespan")
        if isinstance(timespan, dict):
            bob = timespan.get("begin_of_the_begin")
            eoe = timespan.get("end_of_the_end")
            for candidate in (bob, eoe):
                if isinstance(candidate, str) and len(candidate) >= 4 and candidate[:4].isdigit():
                    year = int(candidate[:4])
                    presenting_date = candidate[:10]
                    break

    dating["year"] = year
    if presenting_date:
        dating["presentingDate"] = presenting_date

    # Image
    web_image: Dict[str, str] = {}
    img = _linked_art_image_url(raw)
    if img:
        web_image["url"] = img

    # Placeholder keys (future mapping)
    materials: List[str] = []
    techniques: List[str] = []
    production_places: List[str] = []

    # Attribution
    attribution = _classify_attribution(raw, principal)

    return {
        "objectNumber": object_number,
        "title": title,
        "principalOrFirstMaker": principal,
        "dating": dating,
        "materials": materials,
        "techniques": techniques,
        "productionPlaces": production_places,
        "links": links,
        "webImage": web_image,
        "_attribution": attribution,
    }


# ============================================================
# Public API used by the Streamlit UI
# ============================================================

def resolve_objectnumber_to_pid(session: requests.Session, object_number: str) -> str:
    """
    Resolve an SK-... objectNumber to a PID URL using supported parameters (no q=).
    """
    for field in ("identifier", "objectNumber", "inventoryNumber", "description", "title"):
        resp = session.get(SEARCH_URL, params={field: object_number}, timeout=SEARCH_TIMEOUT)

        if not resp.ok:
            if "Unsupported query parameter" in resp.text:
                continue
            raise RijksAPIError(f"Search API error ({resp.status_code}) via {field}: {resp.text[:200]}")

        data = resp.json()
        items = data.get("orderedItems") or data.get("items") or []
        if items:
            pid = items[0].get("id")
            if isinstance(pid, str) and pid.strip():
                return pid

    raise RijksAPIError(f"Could not resolve objectNumber={object_number} to PID.")


def fetch_metadata_by_objectnumber(object_number: str) -> Dict[str, Any]:
    """
    Fetch raw Linked Art JSON for a given objectNumber (SK-...).
    Useful for DEV tools (hidden unless DEV_MODE=true).
    """
    session = _get_session()
    pid = resolve_objectnumber_to_pid(session, object_number)
    return _fetch_linked_art_json(session, pid)


def extract_year(dating: Dict[str, Any]) -> Optional[int]:
    """Extract numeric year from dating dict."""
    if not isinstance(dating, dict):
        return None
    y = dating.get("year")
    if isinstance(y, int):
        return y
    pd = dating.get("presentingDate")
    if isinstance(pd, str) and pd[:4].isdigit():
        try:
            return int(pd[:4])
        except Exception:
            return None
    return None


def get_best_image_url(art: Dict[str, Any]) -> Optional[str]:
    """Return the best UI image URL from the mapped dict."""
    web = art.get("webImage") or {}
    if isinstance(web, dict):
        url = web.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def search_artworks(
    query: str,
    object_type: Optional[str] = None,
    sort: str = "relevance",
    page_size: int = 12,
    page: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    High-level search:
    1) Search -> PIDs
    2) Resolve -> Linked Art JSON
    3) Map -> UI dict
    4) Local sort + local pagination
    """
    session = _get_session()

    norm = SearchParams(
        query=query.strip(),
        object_type=object_type,
        sort=(sort or "relevance").lower(),
        page_size=min(int(page_size), MAX_RESULTS_PER_SEARCH),
        page=max(int(page), 1),
    )

    if not norm.query:
        return [], 0

    pids = _search_ids(session, norm.query, limit=norm.page_size)
    if not pids:
        return [], 0

    raw_objects: List[Dict[str, Any]] = []
    for pid in pids:
        try:
            raw_objects.append(_fetch_linked_art_json(session, pid))
        except RijksAPIError as exc:
            print(f"[rijks_api] Warning: failed to fetch {pid}: {exc}")

    mapped: List[Dict[str, Any]] = []
    for raw in raw_objects:
        try:
            mapped.append(_map_linked_art_to_legacy_dict(raw))
        except Exception as exc:
            print(f"[rijks_api] Warning: failed to map object: {exc}")

    def _sort_key(art: Dict[str, Any]):
        artist = (art.get("principalOrFirstMaker") or "").lower()
        title = (art.get("title") or "").lower()
        year = extract_year(art.get("dating") or {}) or 10**9

        if norm.sort in ("relevance", "artist"):
            return (artist, title)
        if norm.sort == "title":
            return (title, artist)
        if norm.sort == "chronologic":
            return (year, artist, title)
        if norm.sort == "achronologic":
            return (-year, artist, title)
        return (artist, title)

    mapped.sort(key=_sort_key)

    total = len(mapped)
    start = (norm.page - 1) * norm.page_size
    end = start + norm.page_size
    return mapped[start:end], total