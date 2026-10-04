from types import SimpleNamespace

import pytest

from app.orchestrator import ModelUnavailable
from app.schema_linking import link_schema, link_schema_with_model_chain


def make_response(content):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_link_schema_parses_well_formed_json():
    captured = {}

    def complete_fn(model, messages, tools):
        captured["model"] = model
        captured["tools"] = tools
        return make_response(
            '{"tables": ["dim_movies"], "columns": ["titulo"], "reasoning": "pergunta sobre filmes"}'
        )

    result = link_schema(complete_fn, "model-a:free", "Quais filmes...?", "- dim_movies(titulo)")

    assert result == {
        "tables": ["dim_movies"],
        "columns": ["titulo"],
        "reasoning": "pergunta sobre filmes",
    }
    assert captured["model"] == "model-a:free"
    assert captured["tools"] == []


def test_link_schema_strips_markdown_code_fences():
    def complete_fn(model, messages, tools):
        return make_response(
            '```json\n{"tables": ["dim_movies"], "columns": [], "reasoning": "r"}\n```'
        )

    result = link_schema(complete_fn, "model-a:free", "pergunta", "schema")

    assert result["tables"] == ["dim_movies"]


def test_link_schema_fills_missing_keys_with_defaults():
    def complete_fn(model, messages, tools):
        return make_response('{"tables": ["dim_movies"]}')

    result = link_schema(complete_fn, "model-a:free", "pergunta", "schema")

    assert result == {"tables": ["dim_movies"], "columns": [], "reasoning": ""}


def test_link_schema_raises_on_invalid_json():
    def complete_fn(model, messages, tools):
        return make_response("isso não é json")

    with pytest.raises(ValueError):
        link_schema(complete_fn, "model-a:free", "pergunta", "schema")


def test_link_schema_returns_empty_list_when_tables_is_null():
    def complete_fn(model, messages, tools):
        return make_response('{"tables": null, "columns": null, "reasoning": "r"}')

    result = link_schema(complete_fn, "model-a:free", "pergunta", "schema")

    assert result == {"tables": [], "columns": [], "reasoning": "r"}


def test_link_schema_filters_out_non_string_table_entries():
    def complete_fn(model, messages, tools):
        return make_response(
            '{"tables": [{"name": "dim_movies"}, "dim_genres"], "columns": [], "reasoning": "r"}'
        )

    result = link_schema(complete_fn, "model-a:free", "pergunta", "schema")

    assert result["tables"] == ["dim_genres"]


def test_link_schema_coerces_non_string_reasoning():
    def complete_fn(model, messages, tools):
        return make_response('{"tables": [], "columns": [], "reasoning": 42}')

    result = link_schema(complete_fn, "model-a:free", "pergunta", "schema")

    assert result["reasoning"] == "42"


def test_link_schema_includes_history_between_system_and_question(monkeypatch):
    captured = {}

    def complete_fn(model, messages, tools):
        captured["messages"] = messages
        return make_response('{"tables": [], "columns": [], "reasoning": "r"}')

    history = [
        {"role": "user", "content": "pergunta anterior"},
        {"role": "assistant", "content": "resposta anterior"},
    ]

    link_schema(complete_fn, "model-a:free", "e o segundo?", "schema", history=history)

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1:3] == history
    assert messages[-1] == {"role": "user", "content": "e o segundo?"}


def test_link_schema_with_model_chain_escalates_on_model_unavailable():
    calls = []

    def complete_fn(model, messages, tools):
        calls.append(model)
        if model == "model-a:free":
            raise ModelUnavailable("429 upstream")
        return make_response('{"tables": ["dim_movies"], "columns": [], "reasoning": "r"}')

    result = link_schema_with_model_chain(
        complete_fn, ["model-a:free", "model-b:free"], "pergunta", "schema"
    )

    assert result["tables"] == ["dim_movies"]
    assert calls == ["model-a:free", "model-b:free"]


def test_link_schema_with_model_chain_raises_when_all_models_fail():
    def complete_fn(model, messages, tools):
        raise ModelUnavailable("429 upstream")

    with pytest.raises(ModelUnavailable):
        link_schema_with_model_chain(complete_fn, ["model-a:free", "model-b:free"], "pergunta", "schema")
