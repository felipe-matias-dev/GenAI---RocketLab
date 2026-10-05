import httpx

from app import model_catalog
from app.model_catalog import filter_chain, resolve_model_chain

CATALOG = {
    "vivo/com-tools:free": {"tools", "temperature"},
    "vivo/sem-tools:free": {"temperature"},
}


def test_keeps_models_listed_with_tool_support_in_order():
    kept, dropped = filter_chain(["vivo/com-tools:free"], CATALOG)
    assert kept == ["vivo/com-tools:free"]
    assert dropped == []


def test_drops_retired_models_and_models_without_tools():
    chain = ["aposentado/x:free", "vivo/com-tools:free", "vivo/sem-tools:free"]
    kept, dropped = filter_chain(chain, CATALOG)
    assert kept == ["vivo/com-tools:free"]
    assert dropped == ["aposentado/x:free", "vivo/sem-tools:free"]


def test_other_providers_are_never_checked_against_openrouter_catalog():
    # O catálogo do OpenRouter não lista modelos do Groq — descartá-los por
    # isso apagaria justamente a reserva da cadeia.
    kept, _ = filter_chain(["aposentado/x:free", "groq:openai/gpt-oss-120b"], CATALOG)
    assert kept == ["groq:openai/gpt-oss-120b"]


def test_unavailable_catalog_keeps_chain_untouched():
    chain = ["qualquer/modelo:free"]
    assert filter_chain(chain, None) == (chain, [])


def test_keeps_configured_chain_when_every_model_would_be_dropped():
    chain = ["aposentado/a:free", "aposentado/b:free"]
    kept, dropped = filter_chain(chain, CATALOG)
    assert kept == chain
    assert dropped == chain


def test_disabled_check_does_not_fetch_catalog():
    def must_not_fetch():
        raise AssertionError("não deveria consultar o catálogo")

    assert resolve_model_chain(["a:free"], check_enabled=False, fetch_catalog=must_not_fetch) == ["a:free"]


def test_enabled_check_filters_with_fetched_catalog():
    chain = ["aposentado/x:free", "vivo/com-tools:free"]
    assert resolve_model_chain(chain, check_enabled=True, fetch_catalog=lambda: CATALOG) == [
        "vivo/com-tools:free"
    ]


def test_fetch_parses_openrouter_payload(monkeypatch):
    payload = {"data": [{"id": "m:free", "supported_parameters": ["tools"]}, {"id": "n:free"}]}

    def fake_get(url, timeout):
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(model_catalog.httpx, "get", fake_get)
    assert model_catalog.fetch_openrouter_catalog() == {"m:free": {"tools"}, "n:free": set()}


def test_fetch_returns_none_on_network_error(monkeypatch):
    def failing_get(url, timeout):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(model_catalog.httpx, "get", failing_get)
    assert model_catalog.fetch_openrouter_catalog() is None


def test_fetch_returns_none_on_unexpected_payload(monkeypatch):
    def fake_get(url, timeout):
        return httpx.Response(200, json={"erro": "x"}, request=httpx.Request("GET", url))

    monkeypatch.setattr(model_catalog.httpx, "get", fake_get)
    assert model_catalog.fetch_openrouter_catalog() is None
