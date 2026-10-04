from types import SimpleNamespace

import pytest

from app.schema_linking import link_schema


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
