"""Etapa leve de schema linking: identifica tabelas/colunas provavelmente
relevantes para a pergunta, antes do loop principal de tool-calling.

Deliberadamente não usa nenhum framework de agentes — é só mais uma chamada
ao mesmo client OpenRouter já usado pelo orchestrator (via `complete_fn`),
pedindo uma resposta em JSON estrito. É uma dica consumida pelo prompt de
sistema e exposta no campo `schema_link` da resposta da API, nunca uma
restrição: o resultado não é validado contra o schema real nem usado para
montar ou liberar execução de SQL — `app/guardrails.py` continua sendo a
única fronteira de segurança.
"""

import json
import re
from typing import Callable, Optional

from app.orchestrator import ModelUnavailable

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_PROMPT_TEMPLATE = """\
Você é um especialista em schema linking para um banco de dados de filmes.
Dada a conversa e a pergunta do usuário, e o schema disponível, responda \
APENAS com um JSON estrito (sem markdown, sem texto antes ou depois) no \
formato:
{{"tables": ["tabela1", ...], "columns": ["coluna1", ...], "reasoning": "..."}}

Schema disponível:
{schema}
"""


def link_schema(
    complete_fn: Callable[[str, list[dict], list[dict]], object],
    model: str,
    question: str,
    schema_description: str,
    history: Optional[list[dict]] = None,
) -> dict:
    """Pede ao modelo quais tabelas/colunas são relevantes para `question`.

    `history` (os turnos anteriores da sessão, no mesmo formato usado pelo
    orchestrator principal) é incluído para que perguntas de seguimento
    como "e o segundo?" tenham contexto suficiente para o schema linking
    funcionar — sem ele, cada pergunta era avaliada isolada.

    Levanta ValueError se a resposta não for um JSON válido, ou
    ModelUnavailable se `complete_fn` sinalizar erro de infraestrutura —
    quem chama decide o fallback (ver `link_schema_with_model_chain` e
    `Orchestrator.ask`, que caem para o schema completo e
    `schema_link=None` em caso de falha).
    """
    messages = [{"role": "system", "content": _PROMPT_TEMPLATE.format(schema=schema_description)}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    response = complete_fn(model, messages, [])
    content = response.choices[0].message.content or ""
    cleaned = _CODE_FENCE_RE.sub("", content).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Resposta de schema linking não é JSON válido: {content!r}") from exc

    return {
        "tables": _coerce_str_list(parsed.get("tables")),
        "columns": _coerce_str_list(parsed.get("columns")),
        "reasoning": _coerce_str(parsed.get("reasoning", "")),
    }


def link_schema_with_model_chain(
    complete_fn: Callable[[str, list[dict], list[dict]], object],
    model_chain: list[str],
    question: str,
    schema_description: str,
    history: Optional[list[dict]] = None,
) -> dict:
    """Tenta `link_schema` em cada modelo da cadeia, em ordem, escalando em
    caso de `ModelUnavailable` — a mesma política de resiliência do
    orchestrator principal, aplicada à etapa de schema linking. Se todos os
    modelos falharem por infraestrutura, relança o último `ModelUnavailable`
    (quem chama decide o fallback, como em qualquer falha de linking).
    """
    last_error: Optional[ModelUnavailable] = None
    for model in model_chain:
        try:
            return link_schema(complete_fn, model, question, schema_description, history=history)
        except ModelUnavailable as exc:
            last_error = exc
            continue
    raise last_error


def _coerce_str_list(value) -> list[str]:
    """Filtra `value` para uma lista só de strings; [] para qualquer outra forma.

    Modelos gratuitos às vezes devolvem `null` em vez de `[]`, ou uma lista
    de objetos em vez de strings — essa dica é consumida pelo prompt (nunca
    usada para liberar SQL), então o saneamento aqui é suficiente.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _coerce_str(value) -> str:
    if isinstance(value, str):
        return value
    return str(value) if value is not None else ""
