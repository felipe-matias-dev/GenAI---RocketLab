from app import tools


def test_execute_sql_returns_rows_for_valid_query():
    result = tools.execute_tool("execute_sql", {"query": "SELECT titulo FROM dim_movies LIMIT 2"})

    assert result["ok"] is True
    assert len(result["rows"]) == 2
    assert "titulo" in result["rows"][0]


def test_execute_sql_rejects_write_query():
    result = tools.execute_tool("execute_sql", {"query": "DELETE FROM dim_movies"})

    assert result["ok"] is False
    assert "error" in result


def test_semantic_search_routes_to_embeddings_module(monkeypatch):
    captured = {}

    def fake_semantic_search(query, k):
        captured["query"] = query
        captured["k"] = k
        return [{"titulo": "Filme Similar", "sinopse": "..."}]

    monkeypatch.setattr("app.embeddings.semantic_search", fake_semantic_search)

    result = tools.execute_tool(
        "semantic_search_synopses", {"query": "viagem no tempo", "k": 3}
    )

    assert result == {"ok": True, "rows": [{"titulo": "Filme Similar", "sinopse": "..."}]}
    assert captured == {"query": "viagem no tempo", "k": 3}


def test_get_distinct_values_returns_ok_rows():
    result = tools.execute_tool(
        "get_distinct_values", {"table": "dim_genres", "column": "nome_genero"}
    )

    assert result["ok"] is True
    assert "Science Fiction" in result["values"]
    assert result["truncated"] is False


def test_get_distinct_values_with_contains_filters_results():
    result = tools.execute_tool(
        "get_distinct_values",
        {"table": "dim_genres", "column": "nome_genero", "contains": "Fic"},
    )

    assert result["ok"] is True
    assert result["values"] == ["Science Fiction"]


def test_get_distinct_values_returns_error_for_unknown_column():
    result = tools.execute_tool(
        "get_distinct_values", {"table": "dim_genres", "column": "coluna_invalida"}
    )

    assert result["ok"] is False
    assert "error" in result


def test_unknown_tool_returns_error():
    result = tools.execute_tool("tool_que_nao_existe", {})

    assert result["ok"] is False
    assert "error" in result


def test_execute_sql_reports_timeout_to_the_model_instead_of_raising(monkeypatch):
    import sqlite3

    from app import tools

    def slow(*args, **kwargs):
        raise sqlite3.OperationalError("A consulta excedeu 15s e foi interrompida")

    monkeypatch.setattr(tools, "run_query", slow)
    result = tools.execute_tool("execute_sql", {"query": "SELECT 1"})
    assert result["ok"] is False
    assert "excedeu" in result["error"]


def test_execute_sql_passes_timeout_and_row_cap_to_run_query(monkeypatch):
    from app import tools

    seen = {}

    def fake(sql, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(tools, "run_query", fake)
    tools.execute_tool("execute_sql", {"query": "SELECT 1"})
    assert seen["timeout_seconds"] == tools.SQL_TIMEOUT_SECONDS
    assert seen["max_rows"] == tools.DEFAULT_SQL_ROW_LIMIT
