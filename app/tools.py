import sqlite3

from app.db import run_query
from app.guardrails import GuardrailViolation, validate_sql

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "Executa uma consulta SQL de leitura (SELECT/WITH) contra o "
                "banco de dados de filmes da CineData Analytics e retorna as "
                "linhas resultantes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta SQL SELECT/WITH válida para SQLite.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_synopses",
            "description": (
                "Busca filmes por similaridade semântica de sinopse/enredo "
                "(ex.: 'filmes sobre viagem no tempo'), quando a pergunta não "
                "é resolvível por uma consulta estruturada."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Descrição do enredo/tema buscado.",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Número de resultados desejados.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
]


def execute_tool(name: str, arguments: dict) -> dict:
    if name == "execute_sql":
        return _execute_sql(arguments.get("query", ""))
    if name == "semantic_search_synopses":
        return _semantic_search(arguments.get("query", ""), arguments.get("k", 5))
    return {"ok": False, "error": f"Ferramenta desconhecida: {name}"}


def _execute_sql(query: str) -> dict:
    try:
        safe_query = validate_sql(query)
    except GuardrailViolation as exc:
        return {"ok": False, "error": str(exc)}

    try:
        rows = run_query(safe_query)
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "rows": rows}


def _semantic_search(query: str, k: int) -> dict:
    # Import tardio: evita carregar sentence-transformers (pesado) quando o
    # agente nunca usa a busca semântica.
    from app import embeddings

    try:
        rows = embeddings.semantic_search(query, k)
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira resposta de erro para o LLM
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "rows": rows}
