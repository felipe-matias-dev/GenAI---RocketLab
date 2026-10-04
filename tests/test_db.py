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


def test_connection_is_read_only_at_driver_level():
    conn = db.get_connection()
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM dim_movies")
    finally:
        conn.close()
