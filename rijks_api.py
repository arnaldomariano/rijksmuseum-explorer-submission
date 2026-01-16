"""
rijks_api.py — camada de compatibilidade para o backend local.

Antes: fazia chamadas à API do Rijksmuseum.
Agora: delega toda a lógica de busca para local_collection.py,
mas mantém a mesma interface geral que o app já usava.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List

from local_collection import search_collection


def search_rijks_collection(
    query: str = "",
    page: int = 1,
    page_size: int = 12,
    sort: str = "relevance",
    object_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca obras na coleção local, imitando a estrutura da resposta da API.

    Retorna um dicionário do tipo:

        {
            "artObjects": [...],
            "count": total,
            "page": page,
            "page_size": page_size,
        }

    Assim, qualquer código antigo que esperava 'artObjects' e 'count'
    continua funcionando.
    """
    items, total = search_collection(
        query=query,
        page=page,
        page_size=page_size,
        sort=sort,
        object_type=object_type,
    )

    return {
        "artObjects": items,
        "items": items,      # chave extra, por segurança
        "count": total,
        "page": page,
        "page_size": page_size,
    }


# Aliases para outros nomes que possam estar sendo usados no app
def search_collection_compat(
    query: str = "",
    page: int = 1,
    page_size: int = 12,
    sort: str = "relevance",
    object_type: Optional[str] = None,
) -> Dict[str, Any]:
    return search_rijks_collection(query, page, page_size, sort, object_type)


search_collection_api = search_collection_compat
search_artworks = search_rijks_collection


def extract_year(art: dict):
    """
    Tenta extrair um ano (int) do campo 'dating' de uma obra.
    Retorna None se não encontrar.
    """
    if not isinstance(art, dict):
        return None

    dating = art.get("dating") or {}

    # Caso 1: já tenha year numérico
    year = dating.get("year")
    if isinstance(year, int):
        return year

    # Caso 2: extrair dos 4 primeiros dígitos de presentingDate (ex: "1642", "c. 1650")
    presenting = dating.get("presentingDate")
    if isinstance(presenting, str) and len(presenting) >= 4 and presenting[:4].isdigit():
        try:
            return int(presenting[:4])
        except Exception:
            return None

    return None

# ------------------------------------------------------------
# Helper de imagem, usado em várias páginas do app
# ------------------------------------------------------------

def get_best_image_url(art: Dict[str, Any]) -> Optional[str]:
    """
    Retorna a melhor URL de imagem disponível em um dicionário de artwork.

    Tenta, nesta ordem:
      - art["webImage"]["url"]
      - art["headerImage"]["url"]
      - art["image"]["url"]
    """
    if not isinstance(art, dict):
        return None

    for key in ("webImage", "headerImage", "image"):
        block = art.get(key)
        if isinstance(block, dict):
            url = block.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()

    return None