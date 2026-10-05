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


def test_keyword_inside_string_literal_is_not_a_violation():
    # Títulos como "Create" ou "Drop" são dados, não comandos.
    result = validate_sql("SELECT titulo FROM dim_movies WHERE titulo LIKE '%Create%'")
    assert "LIKE '%Create%'" in result


def test_semicolon_inside_string_literal_is_not_a_second_statement():
    result = validate_sql("SELECT titulo FROM dim_movies WHERE titulo = 'a;b'")
    assert "'a;b'" in result


def test_keyword_in_comment_is_ignored_but_real_keyword_after_it_is_caught():
    assert validate_sql("SELECT 1 -- DROP TABLE x").upper().count("DROP") == 0
    with pytest.raises(GuardrailViolation):
        validate_sql("SELECT 1 /* ok */ ; DROP TABLE dim_movies")


def test_limit_word_inside_string_does_not_count_as_limit():
    result = validate_sql("SELECT 'limit' FROM dim_movies")
    assert result.endswith("LIMIT 500")


def test_limit_only_inside_subquery_still_gets_outer_limit():
    result = validate_sql(
        "SELECT * FROM (SELECT * FROM dim_people LIMIT 3000) a "
        "JOIN (SELECT * FROM dim_people LIMIT 3000) b"
    )
    assert result.endswith(") b LIMIT 500")


def test_outer_limit_after_subquery_is_preserved():
    result = validate_sql("SELECT * FROM (SELECT * FROM dim_movies LIMIT 50) a LIMIT 5")
    assert result.upper().count("LIMIT") == 2
    assert result.endswith("LIMIT 5")


def test_trailing_line_comment_does_not_swallow_appended_limit():
    result = validate_sql("SELECT * FROM dim_movies -- todos os filmes")
    assert result.endswith("LIMIT 500")
    assert "--" not in result


def test_unterminated_string_literal_is_rejected():
    with pytest.raises(GuardrailViolation):
        validate_sql("SELECT 'abc FROM dim_movies; DROP TABLE dim_movies")


def test_escaped_quote_inside_literal_is_handled():
    result = validate_sql("SELECT titulo FROM dim_movies WHERE titulo = 'It''s; DROP'")
    assert "It''s; DROP" in result


def test_keyword_hidden_after_quoted_identifier_is_caught():
    with pytest.raises(GuardrailViolation):
        validate_sql('SELECT "titulo" FROM dim_movies WHERE 1=1 AND DELETE')
