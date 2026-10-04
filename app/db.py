import sqlite3
from functools import lru_cache
from pathlib import Path

from app.config import DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Abre uma conexão SQLite em modo somente-leitura no nível do SO.

    Usar a URI ?mode=ro faz o próprio driver recusar qualquer escrita,
    independente de falhas na validação de SQL em guardrails.py.
    """
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_tables(db_path: Path = DB_PATH) -> list[str]:
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        )
        return [row["name"] for row in cur.fetchall()]
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    return [(row["name"], row["type"]) for row in cur.fetchall()]


@lru_cache(maxsize=1)
def get_schema_description(db_path: str = str(DB_PATH)) -> str:
    """Gera uma descrição textual compacta do schema para o prompt de sistema."""
    conn = get_connection(Path(db_path))
    try:
        lines = []
        for table in list_tables(Path(db_path)):
            cols = _table_columns(conn, table)
            col_desc = ", ".join(f"{name} {ctype}" for name, ctype in cols)
            lines.append(f"- {table}({col_desc})")
        return "\n".join(lines)
    finally:
        conn.close()


def get_distinct_values(
    table: str,
    column: str,
    contains: str = None,
    limit: int = 200,
    db_path: Path = DB_PATH,
) -> dict:
    """Retorna valores distintos não nulos de `column` em `table`.

    Usado pela tool homônima para o LLM descobrir a grafia exata de valores
    de texto (ex.: nome de gênero) antes de montar um filtro WHERE — table/
    column não podem usar placeholders `?` do sqlite3, então são validados
    contra o schema real (allow-list) antes de entrar na query interpolada.
    `contains` é um valor, não um identificador, então entra como parâmetro
    `?` normal (LIKE), sem risco de injeção.

    Colunas de alta cardinalidade (nome de pessoa, produtora) têm centenas
    de milhares de valores distintos — sem `contains`, o resultado é
    cortado em `limit` e `truncated=True` avisa que a lista não é completa.
    """
    conn = get_connection(db_path)
    try:
        if table not in list_tables(db_path):
            raise ValueError(f"Tabela desconhecida: {table}")

        columns = {name for name, _ in _table_columns(conn, table)}
        if column not in columns:
            raise ValueError(f"Coluna desconhecida em {table}: {column}")

        query = f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
        params: list = []
        if contains:
            query += f' AND "{column}" LIKE ?'
            params.append(f"%{contains}%")
        query += " LIMIT ?"
        params.append(limit + 1)

        rows = conn.execute(query, params).fetchall()
        values = [row[0] for row in rows]
        truncated = len(values) > limit
        if truncated:
            values = values[:limit]
        return {"values": values, "truncated": truncated}
    finally:
        conn.close()


def run_query(sql: str, db_path: Path = DB_PATH) -> list[dict]:
    """Executa uma query já validada pelo guardrail e retorna linhas como dicts."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(sql)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
