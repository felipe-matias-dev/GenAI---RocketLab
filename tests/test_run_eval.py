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
            "error": "nenhum modelo respondeu",
        }
    ]

    run_eval._write_report(rows)

    content = results_path.read_text(encoding="utf-8")
    assert "nenhum modelo respondeu" in content
