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
from typing import Callable

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

_PROMPT_TEMPLATE = """\
Você é um especialista em schema linking para um banco de dados de filmes.
Dada a pergunta do usuário e o schema disponível, responda APENAS com um
JSON estrito (sem markdown, sem texto antes ou depois) no formato:
{{"tables": ["tabela1", ...], "columns": ["coluna1", ...], "reasoning": "..."}}

Schema disponível:
{schema}

Pergunta do usuário: {question}
"""


def link_schema(
    complete_fn: Callable[[str, list[dict], list[dict]], object],
    model: str,
    question: str,
    schema_description: str,
) -> dict:
    """Pede ao modelo quais tabelas/colunas são relevantes para `question`.

    Levanta ValueError se a resposta não for um JSON válido — quem chama
    decide o fallback (ver `Orchestrator.ask`, que cai para o schema
    completo e `schema_link=None` em caso de falha).
    """
    messages = [
        {
            "role": "system",
            "content": _PROMPT_TEMPLATE.format(schema=schema_description, question=question),
        },
    ]
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
