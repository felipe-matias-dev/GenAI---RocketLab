"""Confere a cadeia de modelos contra o catálogo público do OpenRouter.

Modelos ":free" entram, saem e perdem suporte a tool calling sem aviso. Sem
esta checagem, um modelo aposentado só é descoberto quando uma pergunta real
bate nele (404) — gastando uma requisição da cota e o tempo de timeout. O
catálogo (`GET /api/v1/models`) é público e não consome cota, então vale
consultá-lo uma vez ao iniciar.

A checagem nunca é uma fronteira: se o catálogo não responder, a cadeia
configurada segue intacta; se ela eliminar todos os modelos, a cadeia
configurada também segue (melhor tentar e cair no 404 do que não ter modelo).
"""

import logging
from typing import Callable, Optional

import httpx

from app.config import MODEL_CATALOG_TIMEOUT_SECONDS, OPENROUTER_MODELS_URL
from app.llm import DEFAULT_PROVIDER, split_model

logger = logging.getLogger(__name__)

Catalog = dict[str, set[str]]


def fetch_openrouter_catalog(timeout: float = MODEL_CATALOG_TIMEOUT_SECONDS) -> Optional[Catalog]:
    """id do modelo -> parâmetros suportados; None se o catálogo não responder."""
    try:
        response = httpx.get(OPENROUTER_MODELS_URL, timeout=timeout)
        response.raise_for_status()
        return {
            item["id"]: set(item.get("supported_parameters") or [])
            for item in response.json()["data"]
        }
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Catálogo do OpenRouter indisponível (%s); cadeia mantida como configurada.", exc)
        return None


def filter_chain(chain: list[str], catalog: Optional[Catalog]) -> tuple[list[str], list[str]]:
    """Devolve (mantidos, descartados). Só modelos do OpenRouter são conferidos:
    um modelo de outro provedor (ex.: "groq:...") não aparece nesse catálogo."""
    if catalog is None:
        return list(chain), []

    kept, dropped = [], []
    for model in chain:
        provider, model_id = split_model(model)
        if provider != DEFAULT_PROVIDER or "tools" in catalog.get(model_id, ()):
            kept.append(model)
        else:
            dropped.append(model)

    if not kept:
        logger.warning(
            "Nenhum modelo da cadeia %s está no catálogo com suporte a tools; "
            "mantendo a cadeia configurada.",
            chain,
        )
        return list(chain), dropped
    if dropped:
        logger.warning(
            "Modelos fora do catálogo do OpenRouter ou sem suporte a tools, "
            "removidos da cadeia: %s",
            dropped,
        )
    return kept, dropped


def resolve_model_chain(
    chain: list[str],
    check_enabled: bool,
    fetch_catalog: Optional[Callable[[], Optional[Catalog]]] = None,
) -> list[str]:
    if not check_enabled:
        return list(chain)
    catalog = (fetch_catalog or fetch_openrouter_catalog)()
    kept, _ = filter_chain(chain, catalog)
    return kept
