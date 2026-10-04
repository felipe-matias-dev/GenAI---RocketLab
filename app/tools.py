import sqlite3

from app.db import get_distinct_values, run_query
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
    {
        "type": "function",
        "function": {
            "name": "get_distinct_values",
            "description": (
                "Lista os valores distintos de uma coluna de texto (ex.: "
                "nome de gênero, de pessoa ou de produtora) para descobrir a "
                "grafia exata usada no banco antes de montar um filtro WHERE."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "Nome da tabela a inspecionar.",
                    },
                    "column": {
                        "type": "string",
                        "description": "Nome da coluna de texto a inspecionar.",
                    },
                    "contains": {
                        "type": "string",
                        "description": (
                            "Opcional. Filtra os valores retornados para os que "
                            "contêm este trecho (case-sensitive). Use para colunas "
                            "de alta cardinalidade (nome de pessoa, produtora) — "
                            "sem filtro, a lista é cortada e pode não conter o "
                            "valor procurado."
                        ),
                    },
                },
                "required": ["table", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_answer",
            "description": (
                "Conclui o turno com a resposta final em linguagem natural, "
                "um score de confiança e o raciocínio que levou à resposta. "
                "Deve ser chamada para encerrar toda resposta, mesmo uma "
                "recusa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "Resposta final em linguagem natural (pt-BR).",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confiança na resposta, de 0.0 a 1.0.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Raciocínio resumido que levou a essa resposta.",
                    },
                },
                "required": ["answer", "confidence", "reasoning"],
            },
        },
    },
]
# "finalize_answer" é terminal: não tem branch em execute_tool() porque o
# orchestrator a intercepta dentro do loop de tool-calling (ver
# _run_with_model em app/orchestrator.py) antes de qualquer chamada chegar
# até aqui — ela nunca é despachada como uma tool comum.


def execute_tool(name: str, arguments: dict) -> dict:
    if name == "execute_sql":
        return _execute_sql(arguments.get("query", ""))
    if name == "semantic_search_synopses":
        return _semantic_search(arguments.get("query", ""), arguments.get("k", 5))
    if name == "get_distinct_values":
        return _get_distinct_values(
            arguments.get("table", ""), arguments.get("column", ""), arguments.get("contains")
        )
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


def _get_distinct_values(table: str, column: str, contains: str = None) -> dict:
    try:
        result = get_distinct_values(table, column, contains=contains)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    except sqlite3.Error as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "values": result["values"], "truncated": result["truncated"]}


def _semantic_search(query: str, k: int) -> dict:
    # Import tardio: evita carregar sentence-transformers (pesado) quando o
    # agente nunca usa a busca semântica.
    from app import embeddings

    try:
        rows = embeddings.semantic_search(query, k)
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira resposta de erro para o LLM
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "rows": rows}
