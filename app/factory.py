from app.cache import ResponseCache
from app.config import CACHE_PATH, MAX_SESSION_TURNS, MAX_TOOL_ITERATIONS, MODEL_CHAIN
from app.llm import complete, get_client
from app.memory import SessionMemory
from app.orchestrator import Orchestrator
from app.tools import execute_tool


def build_orchestrator() -> Orchestrator:
    """Monta o Orchestrator de produção (usado por app/main.py e eval/run_eval.py)."""
    client = get_client()

    def _complete_fn(model: str, messages: list[dict], tools: list[dict]):
        return complete(client, model, messages, tools)

    return Orchestrator(
        complete_fn=_complete_fn,
        tool_executor=execute_tool,
        memory=SessionMemory(max_turns=MAX_SESSION_TURNS),
        cache=ResponseCache(CACHE_PATH),
        model_chain=MODEL_CHAIN,
        max_iterations=MAX_TOOL_ITERATIONS,
    )
