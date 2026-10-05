import sqlite3

import pytest

from app import db


def test_schema_description_lists_known_tables():
    description = db.get_schema_description()
    assert "dim_movies" in description
    assert "fact_movies_performance" in description


def test_run_query_returns_rows():
    rows = db.run_query("SELECT titulo FROM dim_movies LIMIT 3")
    assert len(rows) == 3
    assert "titulo" in rows[0]


def test_explain_query_executes_through_run_query():
    from app.guardrails import validate_sql

    safe_query = validate_sql("EXPLAIN SELECT titulo FROM dim_movies")
    rows = db.run_query(safe_query)
    assert len(rows) > 0


def test_get_distinct_values_returns_known_genre():
    result = db.get_distinct_values("dim_genres", "nome_genero")
    assert "Science Fiction" in result["values"]
    assert result["truncated"] is False


def test_get_distinct_values_with_contains_filters_results():
    result = db.get_distinct_values("dim_genres", "nome_genero", contains="Fic")
    assert result["values"] == ["Science Fiction"]


def test_get_distinct_values_sets_truncated_flag_when_limit_reached():
    # dim_people.nome_pessoa tem centenas de milhares de valores distintos —
    # bem mais que o limit padrão, então sem filtro o resultado é cortado.
    result = db.get_distinct_values("dim_people", "nome_pessoa", limit=5)
    assert len(result["values"]) == 5
    assert result["truncated"] is True


def test_get_distinct_values_is_case_insensitive_for_table_and_column():
    # SQLite resolve identificadores de tabela/coluna sem diferenciar
    # maiúsculas/minúsculas mesmo entre aspas duplas — a validação por
    # allow-list não devia ser mais estrita que o próprio banco.
    result = db.get_distinct_values("DIM_GENRES", "NOME_GENERO")
    assert "Science Fiction" in result["values"]


def test_get_distinct_values_rejects_unknown_table():
    with pytest.raises(ValueError):
        db.get_distinct_values("tabela_que_nao_existe", "nome_genero")


def test_get_distinct_values_rejects_unknown_column():
    with pytest.raises(ValueError):
        db.get_distinct_values("dim_genres", "coluna_que_nao_existe")


def test_get_known_identifiers_includes_real_tables_and_columns():
    known = db.get_known_identifiers()
    assert "dim_movies" in known["tables"]
    assert "titulo" in known["columns"]
    assert "tabela_que_nao_existe" not in known["tables"]


def test_connection_is_read_only_at_driver_level():
    conn = db.get_connection()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM dim_movies")
    finally:
        conn.close()


# Produto cartesiano com LIMIT só nas subqueries: o guardrail antigo o aceitava
# e ele passava de 20s carregando milhões de linhas em memória.
_CARTESIAN = (
    "SELECT * FROM (SELECT * FROM dim_people LIMIT 3000) a "
    "JOIN (SELECT * FROM dim_people LIMIT 3000) b"
)


def test_run_query_interrupts_slow_query_with_timeout():
    with pytest.raises(db.QueryTimeoutError, match="excedeu"):
        db.run_query(_CARTESIAN, timeout_seconds=0.3)


def test_run_query_timeout_error_is_a_sqlite_error():
    # tools._execute_sql só captura sqlite3.Error — o timeout tem que cair lá.
    assert issubclass(db.QueryTimeoutError, sqlite3.Error)


def test_run_query_max_rows_truncates_result():
    rows = db.run_query("SELECT titulo FROM dim_movies", max_rows=7)
    assert len(rows) == 7


def test_run_query_without_limits_keeps_legacy_behaviour():
    rows = db.run_query("SELECT titulo FROM dim_movies LIMIT 600")
    assert len(rows) == 600


@pytest.mark.parametrize(
    "query",
    [
        "SELECT sql FROM sqlite_master LIMIT 5",
        "SELECT * FROM pragma_table_info('dim_movies') LIMIT 5",
        "SELECT load_extension('x') LIMIT 1",
    ],
)
def test_restricted_run_query_blocks_internal_metadata_and_extensions(query):
    with pytest.raises(sqlite3.Error):
        db.run_query(query, timeout_seconds=5)


def test_restricted_run_query_still_allows_regular_queries():
    rows = db.run_query(
        "WITH g AS (SELECT sk_genre_id, nome_genero FROM dim_genres) "
        "SELECT upper(nome_genero) AS genero, (SELECT COUNT(*) FROM dim_movies) AS total FROM g",
        timeout_seconds=10,
        max_rows=100,
    )
    assert len(rows) == 19
    assert rows[0]["total"] == 95645


def test_restricted_run_query_allows_explain_query_plan():
    rows = db.run_query("EXPLAIN QUERY PLAN SELECT titulo FROM dim_movies", timeout_seconds=5)
    assert rows
