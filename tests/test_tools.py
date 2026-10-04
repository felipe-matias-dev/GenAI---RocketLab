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
