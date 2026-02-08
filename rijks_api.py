"""
rijks_api.py — Rijksmuseum Data Services adapter (Linked Art)

Provides a stable "legacy-like" interface for the Streamlit UI:

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

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import streamlit as st


# ============================================================
# Constants
# ============================================================

SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"

SEARCH_TIMEOUT = 20
DETAIL_TIMEOUT = 20

# Upper bound safety (each PID requires a resolver request)
MAX_RESULTS_PER_SEARCH = 120

# Common Rijksmuseum inventory prefixes
CANONICAL_PREFIXES = ("SK-", "RP-", "BK-", "NG-", "AK-", "NM-")


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
# Network probe (used by UI)
# ============================================================

@st.cache_data(show_spinner=False, ttl=24 * 3600)
def probe_image_url(url: str) -> Dict[str, Any]:
    """
    Lightweight validation to distinguish:
      - ok
      - copyright (403/451)
      - broken (404/5xx/not-image/etc.)
    Cached for 24h to avoid repeated network calls.

    Returns a dict shaped for the UI:
      - ok: bool
      - status: "ok" | "copyright" | "broken"
      - http_status: int
      - content_type: str
      - reason: str
    """
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "status": "broken", "http_status": 0, "content_type": "", "reason": "no_url"}

    u = url.strip()
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        # Try HEAD first (cheap)
        r = requests.head(u, timeout=8, allow_redirects=True, headers=headers)
        http_status = int(r.status_code)
        ctype = (r.headers.get("Content-Type") or "").lower().strip()

        # Fallback to GET when HEAD is blocked or missing headers
        if http_status in (405,) or not ctype:
            r = requests.get(u, timeout=10, stream=True, allow_redirects=True, headers=headers)
            http_status = int(r.status_code)
            ctype = (r.headers.get("Content-Type") or "").lower().strip()

        if http_status == 200 and ctype.startswith("image/"):
            return {"ok": True, "status": "ok", "http_status": http_status, "content_type": ctype, "reason": "ok"}

        if http_status in (403, 451):
            return {
                "ok": False,
                "status": "copyright",
                "http_status": http_status,
                "content_type": ctype,
                "reason": "copyright_or_forbidden",
            }

        return {
            "ok": False,
            "status": "broken",
            "http_status": http_status,
            "content_type": ctype,
            "reason": "not_image_or_unavailable",
        }

    except Exception:
        return {"ok": False, "status": "broken", "http_status": 0, "content_type": "", "reason": "request_failed"}


# ============================================================
# classify_work_kind
# ============================================================
def _classify_work_kind(role: Optional[str], object_type_hint: Optional[str] = None) -> str:
    r = (role or "").lower()

    if "photograph" in r or (object_type_hint == "photo"):
        return "photograph"

    # “reproduction” aqui é heurística: gravura/print etc
    if any(k in r for k in ["engraver", "etcher", "printmaker", "lithographer"]):
        return "reproduction"

    if r:
        return "original"

    return "unknown"


# ============================================================
# Search helpers
# ============================================================

def _search_ids(session: requests.Session, query: str, limit: int) -> List[str]:
    """
    Merge results from multiple query fields and dedupe by PID.

    Conservative and predictable:
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


@st.cache_data(show_spinner=False, ttl=7 * 24 * 3600)
def _fetch_linked_art_json_cached(pid_url: str) -> Dict[str, Any]:
    session = _get_session()
    url = f"{pid_url.split('?')[0]}?_profile=la&_mediatype=application/ld+json"
    resp = session.get(url, timeout=DETAIL_TIMEOUT)
    if not resp.ok:
        raise RijksAPIError(
            f"Resolver error for {url} ({resp.status_code}): {resp.text[:200]}"
        )
    obj = resp.json()
    return obj if isinstance(obj, dict) else {}


# ============================================================
# Linked Art utilities (web link, IIIF, HTML)
# ============================================================

def _extract_access_point_url(raw: Dict[str, Any]) -> Optional[str]:
    """Find the first access_point.id anywhere in the Linked Art JSON (recursive)."""

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
    """Extract SK-... from an /object/ URL if present."""
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
    if not isinstance(html, str) or not html:
        return None
    m = re.search(r'https?://[^"\']*iiif[^"\']*/info\.json', html, flags=re.I)
    if m:
        return m.group(0)
    m = re.search(r'https?://[^"\']*iiif[^"\']*/full/[^"\']+', html, flags=re.I)
    if m:
        return m.group(0)
    return None


def _deep_find_iiif_image_url(raw: Dict[str, Any]) -> Optional[str]:
    """
    Find a likely IIIF endpoint URL inside the Linked Art JSON.

    Strategy:
    - Walk whole JSON
    - Collect string URLs
    - Prefer:
        1) .../info.json
        2) anything containing "iiif" (Rijksmuseum endpoints)
    """
    candidates: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str) and node.startswith("http"):
            candidates.append(node)

    walk(raw)

    for url in candidates:
        if url.lower().endswith("/info.json"):
            return url

    for url in candidates:
        if "iiif" in url.lower():
            return url

    return None


def _fetch_public_object_html(url: str, timeout: int = 12) -> Optional[str]:
    """Fetch Rijksmuseum public object page HTML (best effort)."""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if resp.ok and isinstance(resp.text, str) and resp.text.strip():
            return resp.text
    except Exception:
        return None
    return None


def _detect_image_status_from_object_html(html: str) -> str:
    """
    Decide why the image is not available on the public Rijksmuseum page.

    Returns:
        - "copyright"
        - "page_missing"
        - "no_public_image" (default if unsure)
    """
    if not isinstance(html, str) or not html.strip():
        return "no_public_image"

    h = html.lower()

    # Page missing / not found
    if "oeps" in h and ("deze pagina bestaat niet" in h or "pagina bestaat niet" in h):
        return "page_missing"
    if "this page does not exist" in h or "page does not exist" in h:
        return "page_missing"
    if "404" in h and "not found" in h:
        return "page_missing"

    # Copyright
    if "not available because of copyright" in h:
        return "copyright"
    if "not available due to copyright" in h:
        return "copyright"
    if "auteursrecht" in h and ("niet beschikbaar" in h or "niet beschikbaar vanwege" in h):
        return "copyright"
    if "copyright" in h and ("not available" in h or "not available because" in h):
        return "copyright"

    return "no_public_image"


def _extract_artist_from_object_html(html: str) -> Optional[str]:
    """
    Extract maker/artist name from Rijksmuseum public object HTML.

    Tries:
      1) "<role> (artist): <Name>"
      2) "<role>: <Name>" for common roles
      3) "<Name>, 1860 - 1912" near header
    """
    if not isinstance(html, str) or not html:
        return None

    m = re.search(
        r"\b([a-z][a-z\s-]{2,})\s*\(artist\)\s*:\s*([^<\n\r]+)",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        name = m.group(2).strip()
        return name or None

    m = re.search(
        r"\b(painter|artist|maker|draftsman|engraver|designer)\s*:\s*([^<\n\r]+)",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        name = m.group(2).strip()
        return name or None

    m = re.search(
        r"(^|\n)\s*([A-Z][^\n,]{2,}(?:\s+[A-Z][^\n,]{2,})+)\s*,\s*\d{3,4}\s*[-–]\s*\d{3,4}",
        html,
    )
    if m:
        name = m.group(2).strip()
        return name or None

    return None

def _extract_creator_and_role_from_object_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (name, role) from Rijksmuseum public page, if found.

    Examples:
      - "painter (artist): Claude Monet" -> ("Claude Monet", "painter")
      - "engraver: ... " -> ("...", "engraver")
      - "photographer: ..." -> ("...", "photographer")
    """
    if not isinstance(html, str) or not html:
        return None, None

    # 1) role (artist): Name
    m = re.search(
        r"\b([a-z][a-z\s-]{2,})\s*\(artist\)\s*:\s*([^<\n\r]+)",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        role = m.group(1).strip().lower()
        name = m.group(2).strip()
        return (name or None), (role or None)

    # 2) role: Name  (generic)
    m = re.search(
        r"\b(painter|artist|maker|draftsman|engraver|designer|photographer)\s*:\s*([^<\n\r]+)",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        role = m.group(1).strip().lower()
        name = m.group(2).strip()
        return (name or None), (role or None)

    return None, None

# ============================================================
# Image URL extraction (Linked Art -> IIIF)
# ============================================================

def _extract_image_url_from_linked_art(raw: Dict[str, Any]) -> Optional[str]:
    """
    High-level image URL extractor for Linked Art JSON.

    Strategy:
      1) Look for IIIF URL inside JSON
      2) Fallback: access_point HTML -> extract IIIF
      3) Normalize to IIIF JPG
    """
    # 1) Tenta achar um endpoint IIIF diretamente no JSON Linked Art
    iiif = _deep_find_iiif_image_url(raw)
    if iiif:
        return _normalize_iiif_image_url(iiif, width=900)

    # 2) Fallback: usar o access_point da obra e tentar achar IIIF no HTML público
    access_url = _extract_access_point_url(raw)
    if not access_url:
        return None

    html = _fetch_public_object_html(access_url, timeout=12)
    if not html:
        return None

    iiif_html = _extract_iiif_from_html(html)
    if not iiif_html:
        return None

    return _normalize_iiif_image_url(iiif_html, width=900)

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
# Artist extraction (Linked Art)
# ============================================================

def _extract_principal_maker(raw: Dict[str, Any]) -> str:
    """
    Try to extract the main artist name from Linked Art JSON.

    Looks at produced_by.carried_out_by[*] agents:
      - identified_by[*].content
      - _label / label / name

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

        ids = agent.get("identified_by") or []
        if isinstance(ids, list):
            for ident in ids:
                if not isinstance(ident, dict):
                    continue
                content = ident.get("content")
                if isinstance(content, str):
                    add_candidate(content)

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

            parts = prod.get("part") or []
            if isinstance(parts, list):
                for p in parts:
                    scan_produced(p)

        elif isinstance(prod, list):
            for p in prod:
                scan_produced(p)

    scan_produced(raw.get("produced_by"))

    if candidates:
        return candidates[0]

    return "Unknown artist"

def _normalize_maker_name(name: Any) -> str:
    """
    Normalize principal maker labels into a stable UI-friendly value.

    Rules:
      - Keep "anonymous" as "anonymous" (your preference).
      - Convert empty/unknown-ish labels to "Unknown artist".
    """
    s = (name or "")
    if not isinstance(s, str):
        return "Unknown artist"

    s = s.strip()
    if not s:
        return "Unknown artist"

    low = s.lower()

    unknown_tokens = {
        "unknown", "unknown artist",
        "onbekend", "onbekende kunstenaar",
        "n/a", "not specified", "niet vermeld"
    }
    if low in unknown_tokens:
        return "Unknown artist"

    anonymous_tokens = {"anonymous", "anoniem"}
    if low in anonymous_tokens:
        return "anonymous"

    return s


# ============================================================
# Mapper (Linked Art -> legacy-like dict)
# ============================================================

def _normalize_maker_label(name: Any) -> str:
    """
    Normalize maker/artist labels coming from Linked Art or HTML.

    Goals:
    - Keep "anonymous" (when source says Anonymous/Anoniem)
    - Use "Unknown artist" for truly unknown/empty placeholders
    - Otherwise return cleaned name
    """
    if not isinstance(name, str):
        return "Unknown artist"

    n = name.strip()
    if not n:
        return "Unknown artist"

    ln = n.lower()

    unknown_values = {
        "unknown",
        "unknown artist",
        "onbekend",
        "onbekende kunstenaar",
        "n/a",
        "na",
        "niet vermeld",
        "not mentioned",
        "not specified",
        "unspecified",
    }
    if ln in unknown_values:
        return "Unknown artist"

    anonymous_values = {"anonymous", "anoniem"}
    if ln in anonymous_values:
        return "anonymous"

    return n

def _map_linked_art_to_legacy_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map Linked Art JSON-LD into the legacy-like dict used by the Streamlit UI.
    """

    # 1) PID URL
    pid_url: Optional[str] = None
    for key in ("@id", "id"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            pid_url = val.strip()
            break

    # 2) Title
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

    # 3) produced_by (for dating + attribution)
    produced_by = raw.get("produced_by")

    # 4) public url + object number
    access_url = _extract_access_point_url(raw)
    public_url: Optional[str] = _clean_object_page_url(access_url) if access_url else None

    object_number: str = (pid_url or "unknown-id").strip()

    if public_url:
        obj_from_url = _extract_object_number_from_access_point(public_url)
        if isinstance(obj_from_url, str) and obj_from_url.strip():
            object_number = obj_from_url.strip()

    if not any(object_number.startswith(p) for p in CANONICAL_PREFIXES) and isinstance(identified_by, list):
        for ident in identified_by:
            if not isinstance(ident, dict):
                continue
            content = ident.get("content")
            if isinstance(content, str):
                candidate = content.strip()
                if candidate.startswith(CANONICAL_PREFIXES):
                    object_number = candidate
                    break

    if any(object_number.startswith(p) for p in CANONICAL_PREFIXES):
        stable_web_url = f"https://www.rijksmuseum.nl/en/collection/{object_number}"
    elif public_url:
        stable_web_url = public_url
    elif pid_url:
        stable_web_url = pid_url
    else:
        stable_web_url = None

    # 5) principal maker (JSON first, fallback to public HTML only if unknown)
    principal_or_first_maker = _normalize_maker_label(_extract_principal_maker(raw))
    creator_role: Optional[str] = None
    author_note: Optional[str] = None

    if _normalize_maker_name(principal_or_first_maker) == "Unknown artist" and stable_web_url:
        try:
            resp = requests.get(stable_web_url, timeout=DETAIL_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            if resp.ok and isinstance(resp.text, str):
                html_artist = _extract_artist_from_object_html(resp.text)
                if html_artist:
                    principal_or_first_maker = _normalize_maker_label(html_artist)
        except Exception:
            pass

    # Se mesmo após tudo continua Unknown, garanta a nota
    if principal_or_first_maker == "Unknown artist" and not author_note:
        author_note = "Author not specified in museum metadata"

    work_kind = _classify_work_kind(creator_role)

    # 6) dating
    dating: Dict[str, Any] = {"year": None}
    year: Optional[int] = None
    presenting_date: Optional[str] = None

    timespan = produced_by.get("timespan") if isinstance(produced_by, dict) else None
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

    # 7) materials / techniques / places (still optional)
    materials: List[str] = []
    techniques: List[str] = []
    production_places: List[str] = []

    # 8) links
    links: Dict[str, Any] = {}
    if stable_web_url:
        links["web"] = stable_web_url

    # 9) image url + image status (versão leve, sem probe extra)
    web_image: Dict[str, Any] = {}
    img_url = _extract_image_url_from_linked_art(raw)

    if img_url:
        # Temos uma URL de imagem (via JSON ou fallback HTML)
        web_image["url"] = img_url
        image_status = "ok"
    else:
        # Não conseguimos mapear imagem pública via Linked Art + fallback
        # Tenta identificar o motivo olhando a página pública (copyright / page missing)
        image_status = "no_public_image"
        if stable_web_url and "rijksmuseum.nl" in stable_web_url:
            html = _fetch_public_object_html(stable_web_url, timeout=DETAIL_TIMEOUT)
            if html:
                detected = _detect_image_status_from_object_html(html)
                if detected in ("copyright", "page_missing"):
                    image_status = detected

    # 10) attribution tag
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
        "_image_status": image_status,
        "_author_note": author_note,
        "_creator_role": creator_role,
        "_work_kind": work_kind,
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
    """Fetch raw Linked Art JSON for a given objectNumber (SK-...)."""
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
    """Return best image URL available for this artwork."""
    web_image = art.get("webImage") or {}
    if isinstance(web_image, dict):
        url = web_image.get("url")
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

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_fetch_linked_art_json_cached, pid): pid for pid in pids}
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                raw_objects.append(fut.result())
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