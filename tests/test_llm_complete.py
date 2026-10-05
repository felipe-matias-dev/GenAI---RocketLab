from types import SimpleNamespace

import httpx
import openai
import pytest

from app.llm import complete
from app.orchestrator import ModelUnavailable


def _status_error(cls, status_code):
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(status_code=status_code, request=request)
    return cls("boom", response=response, body=None)


def test_complete_returns_response_on_success():
    sentinel = SimpleNamespace(choices=[])
    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return sentinel

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    result = complete(client, "some-model:free", [{"role": "user", "content": "oi"}], [])

    assert result is sentinel
    assert calls["model"] == "some-model:free"


def test_complete_raises_model_unavailable_on_rate_limit():
    class FakeCompletions:
        def create(self, **kwargs):
            raise _status_error(openai.RateLimitError, 429)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with pytest.raises(ModelUnavailable):
        complete(client, "some-model:free", [], [])


def test_complete_raises_model_unavailable_on_server_error():
    class FakeCompletions:
        def create(self, **kwargs):
            raise _status_error(openai.InternalServerError, 500)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with pytest.raises(ModelUnavailable):
        complete(client, "some-model:free", [], [])


def test_complete_omits_tools_kwarg_when_tools_list_is_empty():
    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(choices=[])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    complete(client, "some-model:free", [{"role": "user", "content": "oi"}], [])

    assert "tools" not in calls


def test_complete_includes_tools_kwarg_when_tools_list_is_nonempty():
    calls = {}
    tool_schemas = [{"type": "function", "function": {"name": "execute_sql"}}]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(choices=[])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    complete(client, "some-model:free", [{"role": "user", "content": "oi"}], tool_schemas)

    assert calls["tools"] == tool_schemas


def test_complete_reraises_authentication_error():
    class FakeCompletions:
        def create(self, **kwargs):
            raise _status_error(openai.AuthenticationError, 401)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with pytest.raises(openai.AuthenticationError):
        complete(client, "some-model:free", [], [])


def test_complete_raises_model_unavailable_on_404_for_retired_free_model():
    class FakeCompletions:
        def create(self, **kwargs):
            raise _status_error(openai.NotFoundError, 404)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with pytest.raises(ModelUnavailable):
        complete(client, "retired-model:free", [{"role": "user", "content": "oi"}], [])


def test_complete_raises_model_unavailable_on_413_request_too_large():
    # Groq devolve 413 quando a requisição passa do limite de tokens por
    # minuto do plano gratuito: outro modelo da cadeia pode ter limite maior.
    class FakeCompletions:
        def create(self, **kwargs):
            raise _status_error(openai.APIStatusError, 413)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    with pytest.raises(ModelUnavailable):
        complete(client, "openai/gpt-oss-120b", [], [])


def test_complete_routed_uses_client_of_the_model_prefix():
    from app.llm import complete_routed

    calls = []

    def fake_client(name):
        class FakeCompletions:
            def create(self, **kwargs):
                calls.append((name, kwargs["model"]))
                return SimpleNamespace(choices=[])

        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    clients = {"openrouter": fake_client("openrouter"), "groq": fake_client("groq")}
    complete_routed(clients, "groq:openai/gpt-oss-120b", [], [])
    complete_routed(clients, "qwen/qwen3.8-27b:free", [], [])

    assert calls == [("groq", "openai/gpt-oss-120b"), ("openrouter", "qwen/qwen3.8-27b:free")]


def test_complete_routed_escalates_when_provider_has_no_key():
    from app.llm import complete_routed

    with pytest.raises(ModelUnavailable):
        complete_routed({"openrouter": object()}, "groq:openai/gpt-oss-120b", [], [])
