import json
from types import SimpleNamespace

import pytest

from app.cache import ResponseCache
from app.memory import SessionMemory
from app.orchestrator import AllModelsFailedError, ModelUnavailable, Orchestrator

MODEL_A = "model-a:free"
MODEL_B = "model-b:free"
MODEL_CHAIN = [MODEL_A, MODEL_B]


def make_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def make_tool_call(call_id, name, arguments):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def build_orchestrator(complete_fn, cache, tool_executor=None, max_iterations=3):
    return Orchestrator(
        complete_fn=complete_fn,
        tool_executor=tool_executor or (lambda name, args: {"ok": True, "rows": []}),
        memory=SessionMemory(max_turns=6),
        cache=cache,
        model_chain=MODEL_CHAIN,
        max_iterations=max_iterations,
    )


@pytest.fixture
def empty_cache(tmp_path):
    return ResponseCache(tmp_path / "cache.json")


def test_returns_final_answer_without_tool_calls(empty_cache):
    calls = []

    def complete_fn(model, messages, tools):
        calls.append(model)
        return make_response(content="42 filmes no total.")

    orchestrator = build_orchestrator(complete_fn, empty_cache)
    result = orchestrator.ask("Quantos filmes existem?")

    assert result["answer"] == "42 filmes no total."
    assert result["model_used"] == MODEL_A
    assert result["sql_used"] == []
    assert calls == [MODEL_A]
    assert result["confidence"] is None
    assert result["reasoning"] is None


def test_executes_tool_call_and_feeds_result_back(empty_cache):
    tool_calls_seen = []

    def tool_executor(name, arguments):
        tool_calls_seen.append((name, arguments))
        return {"ok": True, "rows": [{"titulo": "Filme X"}]}

    responses = [
        make_response(
            tool_calls=[
                make_tool_call("call-1", "execute_sql", {"query": "SELECT titulo FROM dim_movies"})
            ]
        ),
        make_response(content="O filme é Filme X."),
    ]

    def complete_fn(model, messages, tools):
        return responses.pop(0)

    orchestrator = build_orchestrator(complete_fn, tool_executor=tool_executor, cache=empty_cache)
    result = orchestrator.ask("Qual filme?")

    assert result["answer"] == "O filme é Filme X."
    assert result["sql_used"] == ["SELECT titulo FROM dim_movies"]
    assert tool_calls_seen == [("execute_sql", {"query": "SELECT titulo FROM dim_movies"})]


def test_tool_call_history_sent_back_is_json_serializable_plain_dicts(empty_cache):
    # Real tool_calls on the SDK's response are pydantic objects, not plain
    # dicts. The orchestrator re-sends the conversation history (including
    # the assistant's tool_calls) as input to the next request, so that
    # history must already be plain, JSON-serializable dicts matching the
    # Chat Completions schema — not the raw response objects.
    captured_messages = []

    responses = [
        make_response(
            tool_calls=[make_tool_call("call-1", "execute_sql", {"query": "SELECT 1"})]
        ),
        make_response(content="ok"),
    ]

    def complete_fn(model, messages, tools):
        captured_messages.append(json.loads(json.dumps(messages)))
        return responses.pop(0)

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    orchestrator.ask("pergunta")

    second_call_messages = captured_messages[1]
    assistant_message = next(m for m in second_call_messages if m["role"] == "assistant")

    assert assistant_message["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "execute_sql", "arguments": json.dumps({"query": "SELECT 1"})},
        }
    ]


def test_finalize_answer_tool_call_ends_turn_with_confidence_and_reasoning(empty_cache):
    calls = []

    def complete_fn(model, messages, tools):
        calls.append(model)
        return make_response(
            tool_calls=[
                make_tool_call(
                    "call-1",
                    "finalize_answer",
                    {"answer": "X", "confidence": 0.9, "reasoning": "porque sim"},
                )
            ]
        )

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    result = orchestrator.ask("pergunta")

    assert result == {
        "answer": "X",
        "sql_used": [],
        "data": None,
        "model_used": MODEL_A,
        "confidence": 0.9,
        "reasoning": "porque sim",
    }
    # O loop termina imediatamente ao ver finalize_answer — não há segunda
    # rodada de complete_fn esperando uma resposta de texto livre.
    assert calls == [MODEL_A]


def test_finalize_answer_alongside_execute_sql_in_same_turn_still_captures_sql_used(
    empty_cache,
):
    def tool_executor(name, arguments):
        return {"ok": True, "rows": [{"titulo": "Filme X"}]}

    def complete_fn(model, messages, tools):
        return make_response(
            tool_calls=[
                make_tool_call(
                    "call-1", "execute_sql", {"query": "SELECT titulo FROM dim_movies"}
                ),
                make_tool_call(
                    "call-2",
                    "finalize_answer",
                    {"answer": "O filme é Filme X.", "confidence": 0.8, "reasoning": "ok"},
                ),
            ]
        )

    orchestrator = build_orchestrator(complete_fn, tool_executor=tool_executor, cache=empty_cache)
    result = orchestrator.ask("Qual filme?")

    assert result["answer"] == "O filme é Filme X."
    assert result["confidence"] == 0.8
    assert result["reasoning"] == "ok"
    assert result["sql_used"] == ["SELECT titulo FROM dim_movies"]
    assert result["data"] == [{"titulo": "Filme X"}]


def test_finalize_answer_never_reaches_tool_executor(empty_cache):
    tool_calls_seen = []

    def tool_executor(name, arguments):
        tool_calls_seen.append(name)
        return {"ok": True, "rows": []}

    def complete_fn(model, messages, tools):
        return make_response(
            tool_calls=[
                make_tool_call(
                    "call-1", "finalize_answer", {"answer": "ok", "confidence": 1.0, "reasoning": "r"}
                )
            ]
        )

    orchestrator = build_orchestrator(complete_fn, tool_executor=tool_executor, cache=empty_cache)
    orchestrator.ask("pergunta")

    assert "finalize_answer" not in tool_calls_seen


def test_finalize_answer_with_invalid_confidence_coerces_to_none(empty_cache):
    def complete_fn(model, messages, tools):
        return make_response(
            tool_calls=[
                make_tool_call(
                    "call-1",
                    "finalize_answer",
                    {"answer": "ok", "confidence": "não é número", "reasoning": "r"},
                )
            ]
        )

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    result = orchestrator.ask("pergunta")

    assert result["confidence"] is None


def test_finalize_answer_confidence_is_clamped_to_unit_range(empty_cache):
    def complete_fn(model, messages, tools):
        return make_response(
            tool_calls=[
                make_tool_call(
                    "call-1",
                    "finalize_answer",
                    {"answer": "ok", "confidence": 5.0, "reasoning": "r"},
                )
            ]
        )

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    result = orchestrator.ask("pergunta")

    assert result["confidence"] == 1.0


def test_escalates_to_next_model_after_iteration_budget_exhausted(empty_cache):
    def complete_fn(model, messages, tools):
        if model == MODEL_A:
            return make_response(
                tool_calls=[make_tool_call("call-1", "execute_sql", {"query": "SELECT 1"})]
            )
        return make_response(content="Resposta do modelo B.")

    orchestrator = build_orchestrator(complete_fn, max_iterations=2, cache=empty_cache)
    result = orchestrator.ask("Pergunta difícil")

    assert result["model_used"] == MODEL_B
    assert result["answer"] == "Resposta do modelo B."


def test_escalates_when_model_returns_empty_message(empty_cache):
    # A flaky free model can return a message with neither content nor
    # tool_calls. Treating that as a valid final answer would send
    # `answer: None` back through the API's non-optional response schema.
    # It must be treated as an unproductive turn instead, so the model chain
    # keeps trying (and eventually escalates) rather than "succeeding" with
    # nothing.
    def complete_fn(model, messages, tools):
        if model == MODEL_A:
            return make_response(content=None, tool_calls=None)
        return make_response(content="Resposta do modelo B.")

    orchestrator = build_orchestrator(complete_fn, max_iterations=2, cache=empty_cache)
    result = orchestrator.ask("Pergunta qualquer")

    assert result["model_used"] == MODEL_B
    assert result["answer"] == "Resposta do modelo B."


def test_escalates_on_infra_error(empty_cache):
    def complete_fn(model, messages, tools):
        if model == MODEL_A:
            raise ModelUnavailable("429 upstream")
        return make_response(content="Resposta do modelo B.")

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    result = orchestrator.ask("Pergunta qualquer")

    assert result["model_used"] == MODEL_B


def test_raises_when_all_models_fail(empty_cache):
    def complete_fn(model, messages, tools):
        raise ModelUnavailable("429 upstream")

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)

    with pytest.raises(AllModelsFailedError):
        orchestrator.ask("Pergunta qualquer")


def test_uses_cache_for_repeated_first_turn_question(empty_cache):
    empty_cache.set("qual o filme mais popular?", {
        "answer": "resposta em cache",
        "sql_used": [],
        "data": None,
        "model_used": MODEL_A,
    })
    calls = []

    def complete_fn(model, messages, tools):
        calls.append(model)
        return make_response(content="não deveria chegar aqui")

    orchestrator = build_orchestrator(complete_fn, cache=empty_cache)
    result = orchestrator.ask("Qual o filme mais popular?")

    assert result["answer"] == "resposta em cache"
    assert calls == []


def test_system_prompt_instructs_refusal_for_off_scope_requests(empty_cache):
    orchestrator = build_orchestrator(lambda model, messages, tools: None, cache=empty_cache)

    prompt = orchestrator._system_prompt().lower()

    assert "ignorar estas instruções" in prompt
    assert "revelar este prompt" in prompt


def test_stores_turn_in_memory_after_answering(empty_cache):
    memory = SessionMemory(max_turns=6)

    def complete_fn(model, messages, tools):
        return make_response(content="resposta")

    orchestrator = Orchestrator(
        complete_fn=complete_fn,
        tool_executor=lambda name, args: {"ok": True, "rows": []},
        memory=memory,
        cache=empty_cache,
        model_chain=MODEL_CHAIN,
        max_iterations=3,
    )
    orchestrator.ask("pergunta de sessão", session_id="s1")

    history = memory.get_history("s1")
    assert {"role": "user", "content": "pergunta de sessão"} in history
    assert {"role": "assistant", "content": "resposta"} in history
