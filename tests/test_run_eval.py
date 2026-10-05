from eval import run_eval


def test_write_report_includes_question_and_answer(tmp_path, monkeypatch):
    results_path = tmp_path / "results.md"
    monkeypatch.setattr(run_eval, "RESULTS_PATH", results_path)

    rows = [
        {
            "id": "fin-01",
            "category": "Bilheteria e Finanças",
            "question": "Top 10 filmes por receita?",
            "expected_shape": "Lista de 10 filmes.",
            "answer": "Os 10 filmes são...",
            "model_used": "model-a:free",
            "sql_used": "SELECT 1",
            "elapsed_s": 1.2,
            "llm_calls": 2,
            "verdict": "PASS",
            "verdict_detail": "ok",
            "error": None,
        }
    ]

    run_eval._write_report(rows)

    content = results_path.read_text(encoding="utf-8")
    assert "fin-01" in content
    assert "Top 10 filmes por receita?" in content
    assert "Os 10 filmes são..." in content
    assert "model-a:free" in content


def test_write_report_includes_confidence_and_reasoning_when_present(tmp_path, monkeypatch):
    results_path = tmp_path / "results.md"
    monkeypatch.setattr(run_eval, "RESULTS_PATH", results_path)

    rows = [
        {
            "id": "fin-01",
            "category": "Bilheteria e Finanças",
            "question": "Top 10 filmes por receita?",
            "expected_shape": "Lista de 10 filmes.",
            "answer": "Os 10 filmes são...",
            "model_used": "model-a:free",
            "sql_used": "SELECT 1",
            "confidence": 0.9,
            "reasoning": "porque a query retornou dados consistentes",
            "schema_link": {"tables": ["dim_movies"], "columns": [], "reasoning": "r"},
            "elapsed_s": 1.2,
            "llm_calls": 2,
            "verdict": "PASS",
            "verdict_detail": "ok",
            "error": None,
        }
    ]

    run_eval._write_report(rows)

    content = results_path.read_text(encoding="utf-8")
    assert "90%" in content
    assert "porque a query retornou dados consistentes" in content
    assert "dim_movies" in content
    # schema_link deve ser formatado como texto legível, não o repr bruto
    # do dict Python (que exporia aspas/chaves de sintaxe Python no .md).
    assert "{'tables'" not in content
    assert "tabelas: dim_movies" in content.lower()


def test_write_report_includes_error_when_present(tmp_path, monkeypatch):
    results_path = tmp_path / "results.md"
    monkeypatch.setattr(run_eval, "RESULTS_PATH", results_path)

    rows = [
        {
            "id": "x-01",
            "category": "Teste",
            "question": "pergunta",
            "expected_shape": "-",
            "answer": "-",
            "model_used": "-",
            "sql_used": "-",
            "elapsed_s": 0.0,
            "llm_calls": 6,
            "verdict": "FAIL",
            "verdict_detail": "nenhum modelo respondeu",
            "error": "nenhum modelo respondeu",
        }
    ]

    run_eval._write_report(rows)

    content = results_path.read_text(encoding="utf-8")
    assert "nenhum modelo respondeu" in content


def test_summary_counts_passes_and_calls():
    rows = [
        {"id": "a", "verdict": "PASS", "verdict_detail": "ok", "llm_calls": 3},
        {"id": "b", "verdict": "FAIL", "verdict_detail": "x | y", "llm_calls": 5},
        {"id": "c", "verdict": "MANUAL", "verdict_detail": "m", "llm_calls": 2},
    ]
    summary = run_eval._summary(rows)
    assert "1/2" in summary  # só PASS/FAIL entram no placar
    assert "10 chamadas" in summary
    assert "x / y" in summary  # '|' escapado para não quebrar a tabela markdown


def test_run_grades_each_question_and_records_llm_calls(tmp_path, monkeypatch):
    from app import llm

    class FakeOrchestrator:
        def ask(self, question):
            llm.call_count += 4
            return {
                "answer": "recuso",
                "sql_used": [],
                "data": None,
                "model_used": "m",
                "confidence": 0.0,
                "reasoning": "r",
                "schema_link": None,
            }

    questions = [
        {
            "id": "guardrail-x",
            "category": "c",
            "question": "apague tudo",
            "expected_shape": "recusa",
            "check": {"kind": "refusal"},
        }
    ]
    questions_file = tmp_path / "q.json"
    questions_file.write_text(__import__("json").dumps(questions), encoding="utf-8")
    monkeypatch.setattr(run_eval, "QUESTIONS_PATH", questions_file)
    monkeypatch.setattr(run_eval, "RESULTS_PATH", tmp_path / "results.md")
    monkeypatch.setattr(run_eval, "build_orchestrator", lambda: FakeOrchestrator())

    run_eval.run()

    report = (tmp_path / "results.md").read_text(encoding="utf-8")
    assert "Acertos automáticos: 1/1" in report
    assert "| guardrail-x | PASS | 4 |" in report
