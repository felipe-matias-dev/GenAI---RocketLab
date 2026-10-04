from types import SimpleNamespace

from app import cli
from app.orchestrator import AllModelsFailedError


class _FakeOrchestrator:
    def __init__(self, responses=None, raise_on=None):
        self._responses = responses or []
        self._raise_on = raise_on or set()
        self.questions_asked = []

    def ask(self, question, session_id=None):
        self.questions_asked.append((question, session_id))
        if question in self._raise_on:
            raise AllModelsFailedError("nenhum modelo respondeu")
        return self._responses.pop(0)


def _scripted_input(lines):
    iterator = iter(lines)

    def fake_input(prompt=""):
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError

    return fake_input


def test_cli_prints_answer_and_metadata(monkeypatch, capsys):
    fake = _FakeOrchestrator(
        responses=[
            {
                "answer": "42 filmes no total.",
                "sql_used": ["SELECT COUNT(*) FROM dim_movies"],
                "data": None,
                "model_used": "model-a:free",
                "confidence": 0.9,
                "reasoning": "contagem direta",
                "schema_link": None,
            }
        ]
    )
    monkeypatch.setattr(cli, "build_orchestrator", lambda: fake)
    monkeypatch.setattr("builtins.input", _scripted_input(["Quantos filmes existem?", "sair"]))

    cli.cli_main()

    out = capsys.readouterr().out
    assert "42 filmes no total." in out
    assert "model-a:free" in out
    assert "0.9" in out or "90%" in out
    assert fake.questions_asked == [("Quantos filmes existem?", "cli")]


def test_cli_exits_cleanly_on_sair(monkeypatch, capsys):
    fake = _FakeOrchestrator(responses=[])
    monkeypatch.setattr(cli, "build_orchestrator", lambda: fake)
    monkeypatch.setattr("builtins.input", _scripted_input(["sair"]))

    cli.cli_main()

    assert fake.questions_asked == []


def test_cli_prints_friendly_message_on_all_models_failed(monkeypatch, capsys):
    fake = _FakeOrchestrator(raise_on={"pergunta difícil"})
    monkeypatch.setattr(cli, "build_orchestrator", lambda: fake)
    monkeypatch.setattr("builtins.input", _scripted_input(["pergunta difícil", "sair"]))

    cli.cli_main()

    out = capsys.readouterr().out
    assert "nenhum modelo respondeu" in out.lower() or "erro" in out.lower()
