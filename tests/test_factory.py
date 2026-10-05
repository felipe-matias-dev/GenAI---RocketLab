from app import factory


def test_disabled_schema_linking_skips_the_extra_llm_call(monkeypatch):
    monkeypatch.setattr(factory, "SCHEMA_LINKING_ENABLED", False)
    monkeypatch.setattr(factory, "get_client", lambda: object())

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("schema linking não deveria chamar o LLM")

    monkeypatch.setattr(factory, "link_schema_with_model_chain", must_not_be_called)
    orchestrator = factory.build_orchestrator()
    assert orchestrator._schema_linker("qualquer pergunta", []) is None


def test_groq_client_joins_only_when_key_is_configured(monkeypatch):
    built = []
    monkeypatch.setattr(factory, "get_client", lambda: built.append("openrouter"))
    monkeypatch.setattr(factory, "get_groq_client", lambda: built.append("groq"))

    monkeypatch.setattr(factory, "GROQ_API_KEY", "")
    factory.build_orchestrator()
    assert built == ["openrouter"]

    built.clear()
    monkeypatch.setattr(factory, "GROQ_API_KEY", "chave")
    factory.build_orchestrator()
    assert built == ["openrouter", "groq"]


def test_orchestrator_receives_chain_filtered_by_catalog(monkeypatch):
    monkeypatch.setattr(factory, "get_client", lambda: object())
    monkeypatch.setattr(factory, "MODEL_CHAIN", ["aposentado:free", "vivo:free"])
    monkeypatch.setattr(factory, "MODEL_CATALOG_CHECK_ENABLED", True)

    from app import model_catalog

    monkeypatch.setattr(
        model_catalog, "fetch_openrouter_catalog", lambda: {"vivo:free": {"tools"}}
    )

    assert factory.build_orchestrator().model_chain == ["vivo:free"]
