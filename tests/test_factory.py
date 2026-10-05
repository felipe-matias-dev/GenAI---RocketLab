from app import factory


def test_disabled_schema_linking_skips_the_extra_llm_call(monkeypatch):
    monkeypatch.setattr(factory, "SCHEMA_LINKING_ENABLED", False)
    monkeypatch.setattr(factory, "get_client", lambda: object())

    def must_not_be_called(*args, **kwargs):
        raise AssertionError("schema linking não deveria chamar o LLM")

    monkeypatch.setattr(factory, "link_schema_with_model_chain", must_not_be_called)
    orchestrator = factory.build_orchestrator()
    assert orchestrator._schema_linker("qualquer pergunta", []) is None
