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
