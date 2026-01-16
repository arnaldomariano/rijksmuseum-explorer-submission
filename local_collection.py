# local_collection.py

"""
Local collection backend for Rijksmuseum Explorer (versão “regularizada”).

Em vez de consultar a API online (que foi desativada), este módulo
carrega uma coleção local de obras de arte de um arquivo JSON e
oferece funções simples de busca, filtro e paginação.

Formato esperado do arquivo data/collection_sample.json:

[
  {
    "objectNumber": "SK-A-1505",
    "title": "The Night Watch",
    "longTitle": "The Night Watch, Rembrandt van Rijn, 1642",
    "principalOrFirstMaker": "Rembrandt van Rijn",
    "dating": { "presentingDate": "1642", "year": 1642 },
    "objectTypes": ["painting"],
    "materials": ["oil paint", "canvas"],
    "techniques": [],
    "productionPlaces": ["Amsterdam"],
    "links": { "web": "https://www.rijksmuseum.nl/en/collection/SK-A-1505" },
    "webImage": { "url": "https://..." }       # opcional
  },
  ...
]

Se você já tem um favorites.json antigo com obras completas, dá para reaproveitar
esses registros copiando os valores (dicts) para dentro de um array.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# Caminho padrão: data/collection_sample.json, relativo ao projeto
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_FILE = DATA_DIR / "collection_sample.json"


@lru_cache(maxsize=1)
def load_collection() -> List[Dict[str, Any]]:
    """
    Carrega a coleção local do arquivo JSON.

    Retorna uma lista de dicionários (cada um representa uma obra).
    Se o arquivo não existir ou estiver inválido, retorna lista vazia.
    """
    try:
        if not DATA_FILE.exists():
            return []

        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)

        # Aceita tanto lista quanto dict (objectNumber -> obra)
        if isinstance(data, list):
            # Garante que cada item é dict
            return [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            return [
                art for art in data.values()
                if isinstance(art, dict)
            ]
        else:
            return []
    except Exception:
        # Nunca quebrar a app por causa da base local
        return []


def _normalize_text(value: Any) -> str:
    if isinstance(value, str):
        return value.lower()
    return ""


def _get_year(art: Dict[str, Any]) -> Optional[int]:
    """Extrai um ano numérico para ordenação (quando disponível)."""
    dating = art.get("dating") or {}
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


def _matches_query(art: Dict[str, Any], query: str) -> bool:
    """
    Verifica se a obra corresponde ao termo de busca (query).

    Procuramos em:
    - title
    - longTitle
    - principalOrFirstMaker
    - materials, techniques, productionPlaces, objectTypes
    """
    q = query.strip().lower()
    if not q:
        return True  # sem termo => tudo entra

    fields: List[str] = []

    for key in ("title", "longTitle", "principalOrFirstMaker"):
        fields.append(_normalize_text(art.get(key)))

    for key in ("materials", "techniques", "productionPlaces", "objectTypes"):
        values = art.get(key) or []
        if isinstance(values, list):
            fields.extend(_normalize_text(v) for v in values)

    haystack = " | ".join(fields)
    return q in haystack


def _matches_object_type(art: Dict[str, Any], object_type: Optional[str]) -> bool:
    """Filtra por tipo de objeto (painting, print, drawing, etc.)."""
    if not object_type:
        return True

    obj_types = art.get("objectTypes") or []
    if not isinstance(obj_types, list):
        return False

    needle = object_type.strip().lower()
    return any(needle in str(t).lower() for t in obj_types)


def _sort_key(art: Dict[str, Any], sort: str):
    """
    Chave de ordenação aproximada.

    sort pode ser:
      - "relevance" (default)  -> artista, título
      - "artist"               -> artista, título
      - "title"                -> título, artista
      - "year_asc"             -> ano crescente
      - "year_desc"            -> ano decrescente
    """
    sort = (sort or "relevance").lower()
    artist = art.get("principalOrFirstMaker") or ""
    title = art.get("title") or ""
    year = _get_year(art)

    if sort in ("relevance", "artist"):
        return (artist.lower(), title.lower())
    elif sort == "title":
        return (title.lower(), artist.lower())
    elif sort == "year_asc":
        # (True/False, valor) para empurrar "sem ano" pro final
        return (year is None, year or 10**9)
    elif sort == "year_desc":
        return (year is None, -(year or -10**9))
    else:
        # fallback
        return (artist.lower(), title.lower())


def search_collection(
    query: str,
    page: int = 1,
    page_size: int = 12,
    sort: str = "relevance",
    object_type: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Faz uma "busca" local dentro da coleção.

    Retorna (items_pagina, total_encontrado).
    """
    all_items = load_collection()

    # Filtro por termo
    filtered = [
        art for art in all_items
        if _matches_query(art, query)
        and _matches_object_type(art, object_type)
    ]

    # Ordenação
    filtered.sort(key=lambda art: _sort_key(art, sort))

    total = len(filtered)

    # Paginação 1-based
    if page < 1:
        page = 1
    if page_size <= 0:
        page_size = 12

    start = (page - 1) * page_size
    end = start + page_size
    page_items = filtered[start:end]

    return page_items, total