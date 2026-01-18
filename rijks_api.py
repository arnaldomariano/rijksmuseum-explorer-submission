"""
Rijksmuseum data access layer (new Data Services version).

This module is used ONLY in the `app_museum_submission` project.

It replaces the old JSON API:
    https://www.rijksmuseum.nl/api/en/collection

with the new Data Services endpoints:
    - Search API: https://data.rijksmuseum.nl/search/collection
    - Linked Data Resolver: dereference each PID (id.rijksmuseum.nl / data.rijksmuseum.nl)

The public functions are designed to keep the same "shape" the Streamlit
app expects:

    - search_artworks(...) -> (list_of_artworks, total_found)
    - extract_year(dating_dict) -> int | None
    - get_best_image_url(artwork_dict) -> str | None

Each "artwork_dict" should contain at least:

    {
        "objectNumber": str,
        "title": str,
        "principalOrFirstMaker": str,
        "dating": {"presentingDate": str, "year": int | None},
        "materials": [str],
        "techniques": [str],
        "productionPlaces": [str],
        "links": {"web": str},
        "webImage": {"url": str}
    }

You will need to adapt `_map_linked_art_to_legacy_dict` after inspecting
the real JSON returned by the Linked Data Resolver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from urllib.parse import urlencode

SEARCH_URL = "https://data.rijksmuseum.nl/search/collection"



# You can tune these for performance
SEARCH_TIMEOUT = 20
DETAIL_TIMEOUT = 20
MAX_RESULTS_PER_SEARCH = 100


class RijksAPIError(RuntimeError):
    """Custom error raised when the Rijksmuseum Data API fails."""


@dataclass
class SearchParams:
    """Normalized search parameters used by this adapter."""
    query: str
    object_type: Optional[str]
    sort: str
    page_size: int
    page: int

def resolve_objectnumber_to_pid(session: requests.Session, object_number: str) -> str:
    """
    Resolve SK-... para PID usando apenas parâmetros aceitos pelo Search endpoint.
    """
    # Tentativas por campos (sem paginação)
    for field in ("identifier", "objectNumber", "inventoryNumber", "description", "title"):
        params = {field: object_number}
        resp = session.get(SEARCH_URL, params=params, timeout=SEARCH_TIMEOUT)

        if not resp.ok:
            # Se o parâmetro não existir, ele vai dizer "Unsupported query parameter: <field>"
            # Aí seguimos para o próximo.
            if "Unsupported query parameter" in resp.text:
                continue
            raise RijksAPIError(
                f"Search API error ({resp.status_code}) via {field}: {resp.text[:200]}"
            )

        data = resp.json()
        items = data.get("orderedItems") or data.get("items") or []
        if items:
            pid = items[0].get("id")
            if isinstance(pid, str) and pid.strip():
                return pid

    raise RijksAPIError(f"Não foi possível resolver objectNumber={object_number} para PID.")
    # 2) fallback (menos confiável, mas funciona em muitos casos)
    for field in ("title", "description"):
        pid = _try(field)
        if pid:
            return pid

    raise RijksAPIError(f"Não foi possível resolver objectNumber={object_number} para PID.")

def build_representations(pid_url: str) -> Dict[str, str]:
    """
    Gera URLs de content negotiation a partir do PID.
    """
    base = pid_url.split("?")[0]
    return {
        "schema_json": f"{base}?_profile=schema&_mediatype=application/json",
        "linkedart_jsonld": f"{base}?_profile=la&_mediatype=application/ld+json",
    }

# -------------------------------------------------------------------
# Low-level HTTP helpers
# -------------------------------------------------------------------
def _get_session() -> requests.Session:
    """
    Create a configured requests.Session.

    Using a session is more efficient than raw requests.get calls.
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "RijksmuseumExplorerSubmission/1.0",
    })
    return session


def _search_ids(
    session: requests.Session,
    query: str,
    page_size: int,
) -> List[str]:
    """
    Call the Search API and return a list of PID URLs (RWO ids).

    IMPORTANTE: este endpoint não aceita 'size' e 'page' (pelo erro 400).
    Então buscamos e limitamos localmente (page_size).
    """
    def _do(field: str) -> List[str]:
        params = {field: query}
        resp = session.get(SEARCH_URL, params=params, timeout=SEARCH_TIMEOUT)
        if not resp.ok:
            raise RijksAPIError(
                f"Search API error ({resp.status_code}) via {field}: {resp.text[:200]}"
            )

        data = resp.json()
        items = data.get("orderedItems") or data.get("items") or []
        ids: List[str] = []
        for item in items[:page_size]:
            pid = item.get("id")
            if isinstance(pid, str):
                ids.append(pid)
        return ids

    for field in ("creator", "title", "description"):
        ids = _do(field)
        if ids:
            return ids

    return []

def _fetch_object_json(
    session: requests.Session,
    pid_url: str,
    mode: str = "linkedart",  # "linkedart" (default) | "schema"
) -> Dict[str, Any]:
    """
    Fetch JSON metadata for a given PID URL.

    mode="linkedart" -> Linked Art (JSON-LD)
    mode="schema"    -> Schema.org (JSON)
    """
    rep = build_representations(pid_url)
    url = rep["linkedart_jsonld"] if mode == "linkedart" else rep["schema_json"]

    resp = session.get(url, timeout=DETAIL_TIMEOUT)
    if not resp.ok:
        raise RijksAPIError(
            f"Resolver error for {url} ({resp.status_code}): {resp.text[:200]}"
        )

    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        raise RijksAPIError(
            f"Resolver returned non-JSON response for {url}: {resp.text[:200]}"
        ) from exc

# -------------------------------------------------------------------
# Mapping from Linked Art JSON to the "legacy" dict used by the app
# -------------------------------------------------------------------
def _map_linked_art_to_legacy_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert the JSON returned by the Linked Data Resolver into a dict
    shaped like the old Rijksmuseum API.

    YOU MUST ADAPT THIS FUNCTION AFTER INSPECTING REAL JSON.

    Use the output of debug_rijks_new_api.py to find the correct paths.

    For now, this is a very conservative placeholder that tries some
    common Linked Art patterns and falls back to empty / 'Unknown'.
    """
    # ------------------------------
    # Object ID (objectNumber)
    # ------------------------------
    # Often the PID itself or a human-readable id is available somewhere.
    # Start with a generic fallback:
    object_number = raw.get("@id") or raw.get("id") or "unknown-id"

    # ------------------------------
    # Title
    # ------------------------------
    title = "Untitled"

    # Many Linked Art objects store titles in 'identified_by'
    # as a list of Name objects with 'content'.
    identified_by = raw.get("identified_by") or []
    if isinstance(identified_by, list):
        for ident in identified_by:
            if not isinstance(ident, dict):
                continue
            content = ident.get("content")
            if isinstance(content, str) and content.strip():
                title = content.strip()
                break

    # ------------------------------
    # Creator / principalOrFirstMaker
    # ------------------------------
    principal_or_first_maker = "Unknown artist"

    produced_by = raw.get("produced_by")
    if isinstance(produced_by, dict):
        carried_out_by = produced_by.get("carried_out_by") or []
        if isinstance(carried_out_by, list) and carried_out_by:
            first_agent = carried_out_by[0]
            if isinstance(first_agent, dict):
                # Agents also often have 'identified_by' list with a Name
                agent_name = None
                agent_ids = first_agent.get("identified_by") or []
                if isinstance(agent_ids, list):
                    for ident in agent_ids:
                        if not isinstance(ident, dict):
                            continue
                        content = ident.get("content")
                        if isinstance(content, str) and content.strip():
                            agent_name = content.strip()
                            break
                if agent_name:
                    principal_or_first_maker = agent_name

    # ------------------------------
    # Dating / year
    # ------------------------------
    dating: Dict[str, Any] = {}
    year: Optional[int] = None
    presenting_date: Optional[str] = None

    timespan = None
    if isinstance(produced_by, dict):
        timespan = produced_by.get("timespan")

    if isinstance(timespan, dict):
        # Many Linked Art timespans have 'begin_of_the_begin' and 'end_of_the_end'
        bob = timespan.get("begin_of_the_begin")
        eoe = timespan.get("end_of_the_end")
        # You can adapt this if you find a better date pattern in the JSON
        # For now, we pick the year part of 'begin_of_the_begin' if present.
        for candidate in (bob, eoe):
            if isinstance(candidate, str) and len(candidate) >= 4 and candidate[:4].isdigit():
                year = int(candidate[:4])
                presenting_date = candidate[:10]  # YYYY-MM-DD
                break

    dating["year"] = year
    if presenting_date:
        dating["presentingDate"] = presenting_date

    # ------------------------------
    # Materials, techniques, production places
    # ------------------------------
    materials: List[str] = []
    techniques: List[str] = []
    production_places: List[str] = []

    # These will depend on the actual Linked Art mapping used by Rijksmuseum.
    # Start with empty lists and fill them after inspecting real JSON.
    # Example placeholders:
    #   materials = ["oil paint", "canvas"]
    #   production_places = ["Amsterdam"]

    # ------------------------------
    # Links + image
    # ------------------------------
    links = {}
    web_image = {}

    # There may be a direct web link or an IIIF manifest in the JSON.
    # You will need to inspect the JSON to decide what to use here.
    # For now we leave them empty.
    # Example (after inspection):
    #   links = {"web": "https://www.rijksmuseum.nl/en/collection/SK-A-1505"}
    #   web_image = {"url": "https://images.rijksmuseum.nl/some-iiif-url/full/400,/0/default.jpg"}

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
    }


# -------------------------------------------------------------------
# Public helpers expected by the Streamlit app
# -------------------------------------------------------------------
def extract_year(dating: Dict[str, Any]) -> Optional[int]:
    """
    Extract a numeric year from the dating dict (if available).
    """
    if not isinstance(dating, dict):
        return None
    y = dating.get("year")
    if isinstance(y, int):
        return y
    presenting = dating.get("presentingDate")
    if isinstance(presenting, str) and presenting[:4].isdigit():
        try:
            return int(presenting[:4])
        except Exception:
            return None
    return None


def get_best_image_url(art: Dict[str, Any]) -> Optional[str]:
    """
    Return the best image URL available for this artwork.

    For now we only look at 'webImage.url', which is the same key used
    by the old JSON API and by the local JSON collection.

    After you discover how the new JSON exposes images (IIIF etc.),
    you can adapt this function to build a proper URL.
    """
    web_image = art.get("webImage") or {}
    if isinstance(web_image, dict):
        url = web_image.get("url")
        if isinstance(url, str) and url.strip():
            return url
    return None


def search_artworks(
    query: str,
    object_type: Optional[str] = None,
    sort: str = "relevance",
    page_size: int = 12,
    page: int = 1,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    High-level search function used by the Streamlit app.

    It:
        - Calls the Search API to get a list of PID URLs.
        - Fetches JSON for each PID via the Resolver.
        - Maps each JSON object into the "legacy" artwork dict.
        - Applies local sorting and simple pagination.

    Returns:
        (artworks, total_found)

    Where:
        - artworks is a list of mapped dicts.
        - total_found is the number of items before local pagination.

    NOTE:
        For now, we only support the first page of the remote Search API
        and do the pagination locally. You can extend this later using the
        'pageToken' mechanism described in the Search docs.
    """
    session = _get_session()

    norm = SearchParams(
        query=query.strip(),
        object_type=object_type,
        sort=(sort or "relevance").lower(),
        page_size=min(page_size, MAX_RESULTS_PER_SEARCH),
        page=max(page, 1),
    )

    if not norm.query:
        return [], 0

    # Step 1: find IDs
    ids = _search_ids(session, norm.query, page_size=norm.page_size)
    if not ids:
        return [], 0

    # Step 2: fetch details for each ID
    raw_objects: List[Dict[str, Any]] = []
    for pid in ids:
        try:
            obj_json = _fetch_object_json(session, pid, mode="linkedart")
            raw_objects.append(obj_json)
        except RijksAPIError as exc:
            # For robustness, log/skip problematic objects instead of breaking everything.
            # In the submission version you might want to log this somewhere.
            print(f"[rijks_api] Warning: failed to fetch {pid}: {exc}")

    # Step 3: map to legacy dicts
    mapped: List[Dict[str, Any]] = []
    for raw in raw_objects:
        try:
            mapped.append(_map_linked_art_to_legacy_dict(raw))
        except Exception as exc:
            print(f"[rijks_api] Warning: failed to map object: {exc}")

    # Step 4: local sort
    def _sort_key(art: Dict[str, Any]):
        artist = art.get("principalOrFirstMaker") or ""
        title = art.get("title") or ""
        year = extract_year(art.get("dating") or {}) or 10**9

        if norm.sort in ("relevance", "artist"):
            return (str(artist).lower(), str(title).lower())
        elif norm.sort == "title":
            return (str(title).lower(), str(artist).lower())
        elif norm.sort == "chronologic":
            return (year, str(artist).lower(), str(title).lower())
        elif norm.sort == "achronologic":
            return (-year, str(artist).lower(), str(title).lower())
        else:
            return (str(artist).lower(), str(title).lower())

    mapped.sort(key=_sort_key)

    total = len(mapped)

    # Step 5: local pagination (1-based)
    start = (norm.page - 1) * norm.page_size
    end = start + norm.page_size
    page_items = mapped[start:end]


    return page_items, total