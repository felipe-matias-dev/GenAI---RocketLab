from app.cache import ResponseCache
from app.config import (
    CACHE_PATH,
    GROQ_API_KEY,
    MAX_SESSION_TURNS,
    MAX_TOOL_ITERATIONS,
    MODEL_CATALOG_CHECK_ENABLED,
    MODEL_CHAIN,
    SCHEMA_LINKING_ENABLED,
)
from app.db import get_schema_description
from app.llm import complete_routed, get_client, get_groq_client
from app.memory import SessionMemory
from app.model_catalog import resolve_model_chain
from app.orchestrator import Orchestrator
from app.schema_linking import link_schema_with_model_chain
from app.tools import execute_tool


def build_orchestrator() -> Orchestrator:
    """Monta o Orchestrator de produção (usado por app/main.py e eval/run_eval.py)."""
    clients = {"openrouter": get_client()}
    if GROQ_API_KEY:
        clients["groq"] = get_groq_client()

    model_chain = resolve_model_chain(MODEL_CHAIN, MODEL_CATALOG_CHECK_ENABLED)

    def _complete_fn(model: str, messages: list[dict], tools: list[dict]):
        return complete_routed(clients, model, messages, tools)

    def _schema_linker(question: str, history: list[dict]) -> dict | None:
        if not SCHEMA_LINKING_ENABLED:
            return None
        return link_schema_with_model_chain(
            _complete_fn, model_chain, question, get_schema_description(), history=history
        )

    return Orchestrator(
        complete_fn=_complete_fn,
        tool_executor=execute_tool,
        memory=SessionMemory(max_turns=MAX_SESSION_TURNS),
        cache=ResponseCache(CACHE_PATH),
        model_chain=model_chain,
        max_iterations=MAX_TOOL_ITERATIONS,
        schema_linker=_schema_linker,
    )
