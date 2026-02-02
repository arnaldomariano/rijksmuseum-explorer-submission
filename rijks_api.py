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
# EXTRACT IMAGE
# ============================================================
def _extract_image_url_from_linked_art(raw: Dict[str, Any]) -> Optional[str]:
    """
    High-level image URL extractor for Linked Art JSON.

    Strategy:
    1) Look for any IIIF-like URL inside the JSON (via `_deep_find_iiif_image_url`).
    2) If not found, look for `access_point` → fetch the HTML and extract IIIF.
    3) Normalize everything to a standard IIIF JPEG URL that Streamlit can display.
    """
    # 1) Try to find an IIIF URL directly in the JSON
    iiif = _deep_find_iiif_image_url(raw)
    if iiif:
        return _normalize_iiif_image_url(iiif, width=600)

    # 2) If no direct IIIF URL, fall back to access_point + HTML scraping
    access_url = _extract_access_point_url(raw)
    if not access_url:
        return None

    try:
        resp = requests.get(access_url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        if not resp.ok or not isinstance(resp.text, str):
            return None

        iiif_html = _extract_iiif_from_html(resp.text)
        if not iiif_html:
            return None

        return _normalize_iiif_image_url(iiif_html, width=900)
    except Exception:
        return None

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

def _extract_artist_from_object_html(html: str) -> Optional[str]:
    """
    Extract the maker/artist name from Rijksmuseum public object HTML.

    The Rijksmuseum "Creation" block can use many role labels, e.g.:
      - painter (artist): Claude Monet
      - draftsman (artist): Jan Jansz. Post
      - engraver (artist): ...
      - maker: ...
      - artist: ...

    We try, in order:
      1) Role-based lines: "<role> (artist): <Name>"
      2) Generic role lines: "<role>: <Name>" (painter:, artist:, maker:, etc.)
      3) Header line just under the title: "<Name>, 1860 - 1912"
    """
    if not isinstance(html, str) or not html:
        return None

    # 1) Most reliable: "role (artist): Name" (covers draftsman (artist), painter (artist), etc.)
    m = re.search(
        r"\b([a-z][a-z\s-]{2,})\s*\(artist\)\s*:\s*([^<\n\r]+)",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        name = m.group(2).strip()
        if name:
            return name

    # 2) Generic "role: Name" (painter:, artist:, maker:, engraver:, etc.)
    m = re.search(r"\b(painter|artist|maker|draftsman|engraver|designer)\s*:\s*([^<\n\r]+)", html, flags=re.IGNORECASE)
    if m:
        name = m.group(2).strip()
        if name:
            return name

    # 3) Fallback: "<Name>, 1860 - 1912" near the header
    m = re.search(
        r"(^|\n)\s*([A-Z][^\n,]{2,}(?:\s+[A-Z][^\n,]{2,})+)\s*,\s*\d{3,4}\s*[-–]\s*\d{3,4}",
        html,
    )
    if m:
        name = m.group(2).strip()
        if name:
            return name

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


def _find_image_url_in_linked_art(data: Any) -> Optional[str]:
    """
    Try to find a usable image URL inside a Linked Art JSON object.

    New heuristic (more permissive):
    - Collect ANY http/https URL.
    - Prefer URLs from Rijksmuseum domains.
    - Skip obvious 1x1 tracking / placeholder images.
    """

    candidates: List[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, str):
            v = node.strip()
            if not v:
                return

            # Only look at something that looks like a URL
            if not ("http://" in v or "https://" in v or v.startswith("//")):
                return

            lower = v.lower()

            # Skip known placeholder / tracking images
            if "1x1" in lower and "static/images" in lower:
                return

            candidates.append(v)

    _walk(data)

    if not candidates:
        return None

    # Normalize protocol-relative URLs (//...)
    norm_candidates: List[str] = []
    for url in candidates:
        u = url.strip()
        if u.startswith("//"):
            u = "https:" + u
        norm_candidates.append(u)

    # Prefer Rijksmuseum domains and anything with 'image' or 'iiif'
    def _score(u: str) -> tuple:
        lu = u.lower()
        return (
            "rijksmuseum" not in lu,           # prefer Rijksmuseum
            "images." not in lu and "image" not in lu and "iiif" not in lu,
            not lu.endswith((".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp")),
            len(u),                            # shorter URLs first
        )

    norm_candidates.sort(key=_score)
    return norm_candidates[0] if norm_candidates else None

def _deep_find_iiif_image_url(raw: Dict[str, Any]) -> Optional[str]:
    """
    Try to find an image URL inside the Linked Art JSON.

    Strategy:
    - Walk the whole JSON (dicts + lists).
    - Collect every string that starts with "http".
    - Prefer URLs that:
        * look like real images (.jpg, .jpeg, .png, .webp, .tif, .tiff), or
        * contain "iiif" and "rijksmuseum" (typical IIIF endpoints).

    This version also prints the first few candidate URLs to the terminal
    so we can inspect what the Data Services is actually returning.
    """
    candidates: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            if node.startswith("http"):
                candidates.append(node)

    # Walk the full JSON tree
    walk(raw)

    # --- DEBUG: print candidates once per object ---
    # (Isso vai aparecer no terminal onde você rodou o Streamlit)
    if candidates:
        print("[rijks_api] Candidate URLs for image (first 10):")
        for url in candidates[:10]:
            print("   ", url)
    else:
        print("[rijks_api] No http-like URLs found in this object JSON")

    # 1) Prefer obvious image URLs by extension
    for url in candidates:
        lower = url.lower()
        if any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")):
            return url

    # 2) Fallback: any IIIF-ish URL from Rijksmuseum
    for url in candidates:
        lower = url.lower()
        if "iiif" in lower and "rijksmuseum" in lower:
            return url

    # 3) Nothing suitable found
    return None

def _extract_principal_maker(raw: Dict[str, Any]) -> str:
    """
    Try to extract the main artist name from Linked Art JSON.

    Strategy:
    1) Look into produced_by.carried_out_by[*] agents.
       - Use identified_by[*].content
       - Or _label / label / name
    2) Accept both dict and list for produced_by / carried_out_by.
    3) Ignore clearly "unknown" labels (Unknown, Onbekend, etc.).

    Returns a non-empty string or "Unknown artist".
    """
    candidates: List[str] = []

    def add_candidate(name: Any) -> None:
        if not isinstance(name, str):
            return
        n = name.strip()
        if not n:
            return
        ln = n.lower()
        if ln in ("unknown", "unknown artist", "onbekend", "onbekende kunstenaar"):
            return
        if n not in candidates:
            candidates.append(n)

    def scan_agent(agent: Any) -> None:
        if not isinstance(agent, dict):
            return

        # 1) identified_by list → content
        ids = agent.get("identified_by") or []
        if isinstance(ids, list):
            for ident in ids:
                if not isinstance(ident, dict):
                    continue
                content = ident.get("content")
                if isinstance(content, str):
                    add_candidate(content)

        # 2) Fallback: _label / label / name
        for key in ("_label", "label", "name"):
            val = agent.get(key)
            if isinstance(val, str):
                add_candidate(val)

    def scan_produced(prod: Any) -> None:
        if isinstance(prod, dict):
            carried = prod.get("carried_out_by") or []
            if not isinstance(carried, list):
                carried = [carried]
            for ag in carried:
                scan_agent(ag)

            # Sometimes there are nested parts with their own carried_out_by
            parts = prod.get("part") or []
            if isinstance(parts, list):
                for p in parts:
                    scan_produced(p)

        elif isinstance(prod, list):
            for p in prod:
                scan_produced(p)

    produced = raw.get("produced_by")
    scan_produced(produced)

    if candidates:
        return candidates[0]

    return "Unknown artist"

def _fallback_creator_name(raw: Dict[str, Any]) -> Optional[str]:
    """
    Try to recover a creator/artist name from anywhere in the Linked Art JSON.

    Strategy:
    1) Walk the JSON recursively.
    2) Look for dicts that have an `identified_by` list with Name objects.
    3) Return the first non-empty `content` that looks like a personal name.

    This is a best-effort fallback when `produced_by.carried_out_by` is missing
    or does not expose the artist in the expected place.
    """
    best: Optional[str] = None

    def walk(node: Any) -> None:
        nonlocal best
        if best is not None:
            # We already found a candidate, no need to keep walking
            return

        if isinstance(node, dict):
            ids = node.get("identified_by") or []
            if isinstance(ids, list):
                for ident in ids:
                    if not isinstance(ident, dict):
                        continue
                    content = ident.get("content")
                    if isinstance(content, str):
                        name = content.strip()
                        # Very light heuristic: avoid 1-word nonsense like "12"
                        if len(name) >= 3 and " " in name:
                            best = name
                            return

            for v in node.values():
                walk(v)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(raw)
    return best

def _map_linked_art_to_legacy_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Linked Art JSON-LD (Rijksmuseum Data Services) into the legacy-like dict
    used by the Streamlit UI.

    Output fields:
      - objectNumber
      - title
      - principalOrFirstMaker
      - dating {year, presentingDate}
      - materials, techniques, productionPlaces (best-effort / optional)
      - links {web}
      - webImage {url}
      - _attribution (research label)
    """

    # ------------------------------------------------------
    # 1) Persistent identifier (PID URL)
    # ------------------------------------------------------
    pid_url: Optional[str] = None
    for key in ("@id", "id"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            pid_url = val.strip()
            break

    # ------------------------------------------------------
    # 2) Title (best effort)
    # ------------------------------------------------------
    title = "Untitled"
    identified_by = raw.get("identified_by") or []
    if isinstance(identified_by, list):
        for ident in identified_by:
            if not isinstance(ident, dict):
                continue
            content = ident.get("content")
            if isinstance(content, str) and content.strip():
                title = content.strip()
                break

    # ------------------------------------------------------
    # 3) produced_by (used later for dating + attribution)
    # ------------------------------------------------------
    produced_by = raw.get("produced_by")

    # ------------------------------------------------------
    # 4) Public page URL (access_point) + objectNumber
    #
    # Goal:
    # - Derive a stable public URL whenever possible.
    # - Derive a human-readable objectNumber (SK- / RP- / BK- / etc.).
    # ------------------------------------------------------
    access_url = _extract_access_point_url(raw)
    public_url: Optional[str] = _clean_object_page_url(access_url) if access_url else None

    # Start with PID as a fallback ID
    object_number: str = (pid_url or "unknown-id").strip()

    # Common Rijksmuseum inventory prefixes
    canonical_prefixes = ("SK-", "RP-", "BK-", "NG-", "AK-", "NM-")

    # 4a) If the access_point URL contains a canonical object number, prefer it
    if public_url:
        obj_from_url = _extract_object_number_from_access_point(public_url)
        if isinstance(obj_from_url, str) and obj_from_url.strip():
            object_number = obj_from_url.strip()

    # 4b) If still not a canonical inventory number, try to recover from identified_by
    if not any(object_number.startswith(p) for p in canonical_prefixes) and isinstance(identified_by, list):
        for ident in identified_by:
            if not isinstance(ident, dict):
                continue
            content = ident.get("content")
            if not isinstance(content, str):
                continue
            candidate = content.strip()
            if candidate.startswith(canonical_prefixes):
                object_number = candidate
                break

    # 4c) Compute a stable web URL:
    # - If we have a canonical inventory number -> use the stable /en/collection/<objectNumber>
    # - Else fall back to the cleaned access_point URL
    # - Else last fallback: PID URL
    stable_web_url: Optional[str] = None
    if any(object_number.startswith(p) for p in canonical_prefixes):
        stable_web_url = f"https://www.rijksmuseum.nl/en/collection/{object_number}"
    elif public_url:
        stable_web_url = public_url
    elif pid_url:
        stable_web_url = pid_url

    # ------------------------------------------------------
    # 5) Main artist name (JSON first)
    # ------------------------------------------------------
    principal_or_first_maker = _extract_principal_maker(raw)

    # Optional fallback via public HTML page (only if still unknown)
    # IMPORTANT: use a stable public URL if we have an object number
    web_url: Optional[str] = None
    if isinstance(object_number, str) and object_number.startswith(canonical_prefixes):
        web_url = f"https://www.rijksmuseum.nl/en/collection/{object_number}"
    elif public_url:
        web_url = public_url
    elif pid_url:
        web_url = pid_url

    if principal_or_first_maker == "Unknown artist" and stable_web_url:
        try:
            resp = requests.get(stable_web_url, timeout=DETAIL_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok and isinstance(resp.text, str):
                html_artist = _extract_artist_from_object_html(resp.text)
                if html_artist:
                    principal_or_first_maker = html_artist
        except Exception:
            pass
    # ------------------------------------------------------
    # 6) Dating / year (best effort)
    # ------------------------------------------------------
    dating: Dict[str, Any] = {"year": None}
    year: Optional[int] = None
    presenting_date: Optional[str] = None

    timespan = None
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

    # ------------------------------------------------------
    # 7) Materials / techniques / production places (optional for now)
    # ------------------------------------------------------
    materials: List[str] = []
    techniques: List[str] = []
    production_places: List[str] = []

    # ------------------------------------------------------
    # 8) Links (stable public URL)
    #
    # We prefer the stable Rijksmuseum collection URL when we have a canonical
    # inventory number (SK-/RP-/BK-/...). Otherwise we fall back to the best
    # public URL we could detect (access_point or PID).
    # ------------------------------------------------------
    links: Dict[str, Any] = {}

    if stable_web_url:
        links["web"] = stable_web_url

    # ------------------------------------------------------
    # 9) Image URL (best effort)
    # ------------------------------------------------------
    web_image: Dict[str, Any] = {}
    img_url = _extract_image_url_from_linked_art(raw)
    if img_url:
        web_image["url"] = img_url

    # ------------------------------------------------------
    # 10) Authorship label (research tag)
    # ------------------------------------------------------
    attribution_tag = _classify_attribution(raw, principal_or_first_maker)

    return {
        "objectNumber": object_number,
        "title": title,
        "principalOrFirstMaker": principal_or_first_maker,
        "dating": dating,
        "materials": materials,
        "techniques": techniques,
        "productionPlaces": production_places,
        "links": links,
        "webImage": web_image,
        "_attribution": attribution_tag,
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
    """
    Return the best image URL available for this artwork.

    For now we look at:
    - art["webImage"]["url"] if present
    - any fallback field "_image_url" if we ever add it in the future
    """
    web_image = art.get("webImage") or {}
    if isinstance(web_image, dict):
        url = web_image.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()

    # Optional future fallback
    url = art.get("_image_url")
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