import pytest

from app.guardrails import GuardrailViolation, validate_sql


def test_accepts_select_query():
    result = validate_sql("SELECT * FROM dim_movies")
    assert result.strip().upper().startswith("SELECT")


def test_accepts_with_cte_query():
    result = validate_sql("WITH x AS (SELECT 1 AS n) SELECT * FROM x")
    assert "SELECT" in result.upper()


def test_rejects_insert():
    with pytest.raises(GuardrailViolation):
        validate_sql("INSERT INTO dim_movies (titulo) VALUES ('x')")


def test_rejects_delete():
    with pytest.raises(GuardrailViolation):
        validate_sql("DELETE FROM dim_movies")


def test_rejects_drop_table():
    with pytest.raises(GuardrailViolation):
        validate_sql("DROP TABLE dim_movies")


def test_rejects_update():
    with pytest.raises(GuardrailViolation):
        validate_sql("UPDATE dim_movies SET titulo = 'x'")


def test_rejects_pragma():
    with pytest.raises(GuardrailViolation):
        validate_sql("PRAGMA table_info(dim_movies)")


def test_rejects_attach():
    with pytest.raises(GuardrailViolation):
        validate_sql("ATTACH DATABASE 'other.db' AS other")


def test_rejects_multiple_statements():
    with pytest.raises(GuardrailViolation):
        validate_sql("SELECT * FROM dim_movies; DROP TABLE dim_movies")


def test_rejects_empty_query():
    with pytest.raises(GuardrailViolation):
        validate_sql("   ")


def test_injects_default_limit_when_missing():
    result = validate_sql("SELECT * FROM dim_movies")
    assert "LIMIT 500" in result.upper()


def test_preserves_existing_limit():
    result = validate_sql("SELECT * FROM dim_movies LIMIT 10")
    assert result.upper().count("LIMIT") == 1
    assert "LIMIT 10" in result.upper()


def test_column_name_containing_keyword_substring_not_rejected():
    # "created_at" contains "create" as a substring but is a column name,
    # not the CREATE keyword — must not be flagged by a naive substring check.
    result = validate_sql("SELECT created_at FROM movie_reviews")
    assert "SELECT" in result.upper()


def test_allows_trailing_semicolon():
    result = validate_sql("SELECT * FROM dim_movies;")
    assert result.strip().endswith(";") is False


def test_accepts_replace_scalar_function_in_select():
    # REPLACE(x, y, z) is a legitimate read-only SQLite string function —
    # distinct from the "REPLACE INTO" / "INSERT OR REPLACE" write forms,
    # which are already rejected by the SELECT/WITH start-anchor check.
    result = validate_sql("SELECT REPLACE(titulo, ' ', '_') FROM dim_movies")
    assert "REPLACE" in result.upper()


def test_still_rejects_replace_into_write_form():
    with pytest.raises(GuardrailViolation):
        validate_sql("REPLACE INTO dim_movies (titulo) VALUES ('x')")


def test_accepts_explain_select():
    result = validate_sql("EXPLAIN SELECT * FROM dim_movies")
    assert result.upper().startswith("EXPLAIN")
    assert "SELECT" in result.upper()


def test_accepts_explain_query_plan_select():
    result = validate_sql("EXPLAIN QUERY PLAN SELECT * FROM dim_movies")
    assert result.upper().startswith("EXPLAIN QUERY PLAN")
    assert "SELECT" in result.upper()


def test_explain_still_rejects_forbidden_keyword():
    with pytest.raises(GuardrailViolation):
        validate_sql("EXPLAIN DELETE FROM dim_movies")
