import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Optional

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


@lru_cache(maxsize=1)
def get_known_identifiers(db_path: str = str(DB_PATH)) -> dict:
    """Conjunto de tabelas e colunas reais do schema (nomes, não valores).

    Usado para filtrar a dica de schema linking (ver app/orchestrator.py)
    contra identificadores que realmente existem, em vez de repassar texto
    sem validação vindo do modelo para o prompt de sistema.
    """
    conn = get_connection(Path(db_path))
    try:
        tables = set(list_tables(Path(db_path)))
        columns = set()
        for table in tables:
            for name, _ in _table_columns(conn, table):
                columns.add(name)
        return {"tables": tables, "columns": columns}
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
        # SQLite resolve identificadores de tabela/coluna sem diferenciar
        # maiúsculas/minúsculas (mesmo entre aspas duplas) — a validação
        # por allow-list não deve ser mais estrita que o próprio banco.
        tables_by_lower = {name.lower(): name for name in list_tables(db_path)}
        if table.lower() not in tables_by_lower:
            raise ValueError(f"Tabela desconhecida: {table}")

        columns_by_lower = {
            name.lower(): name for name, _ in _table_columns(conn, table)
        }
        if column.lower() not in columns_by_lower:
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


class QueryTimeoutError(sqlite3.OperationalError):
    """A consulta excedeu o tempo máximo permitido e foi interrompida."""


class QueryNotAllowedError(sqlite3.OperationalError):
    """A consulta tentou acessar algo fora do que o agente pode ler."""


# Funções que o authorizer nega mesmo dentro de um SELECT.
_DENIED_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit"})

# Quantas instruções da VM do SQLite rodam entre duas checagens do prazo.
_PROGRESS_STEP = 10_000


def _read_only_authorizer(allowed_tables: frozenset[str]):
    """Authorizer do SQLite: só SELECT sobre as tabelas reais do schema.

    Vale para qualquer forma de acesso (tabelas virtuais `pragma_*`,
    `sqlite_master`, funções de extensão), então não depende de regex sobre
    o texto da query — segunda fronteira de segurança além de guardrails.py.
    """

    def authorize(action, arg1, arg2, database, source):
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_READ:
            return sqlite3.SQLITE_OK if arg1 in allowed_tables else sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION:
            denied = (arg2 or "").lower() in _DENIED_FUNCTIONS
            return sqlite3.SQLITE_DENY if denied else sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    return authorize


def run_query(
    sql: str,
    db_path: Path = DB_PATH,
    timeout_seconds: Optional[float] = None,
    max_rows: Optional[int] = None,
) -> list[dict]:
    """Executa uma query já validada pelo guardrail e retorna linhas como dicts.

    Sem `timeout_seconds`/`max_rows` o comportamento é o antigo (sem limites,
    sem authorizer) — usado só por código de confiança, como a indexação das
    sinopses. Quando qualquer limite é passado (caminho do LLM), a execução
    também passa pelo authorizer somente-leitura.

    `max_rows` corta o resultado em memória: um LIMIT numa subquery não
    impede um JOIN de devolver milhões de linhas, então o limite precisa
    existir também do lado de quem lê o cursor.
    """
    conn = get_connection(db_path)
    try:
        restricted = timeout_seconds is not None or max_rows is not None
        if restricted:
            conn.set_authorizer(_read_only_authorizer(frozenset(list_tables(db_path))))
        deadline = None
        if timeout_seconds is not None:
            deadline = time.monotonic() + timeout_seconds
            # Retornar != 0 do handler aborta a query com "interrupted".
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), _PROGRESS_STEP)
        try:
            cur = conn.execute(sql)
            fetched = cur.fetchmany(max_rows) if max_rows is not None else cur.fetchall()
        except sqlite3.DatabaseError as exc:
            if deadline is not None and "interrupted" in str(exc).lower():
                raise QueryTimeoutError(
                    f"A consulta excedeu {timeout_seconds:g}s e foi interrompida; "
                    "simplifique-a (menos JOINs, filtre antes de juntar)."
                ) from exc
            if "not authorized" in str(exc).lower():
                raise QueryNotAllowedError(
                    "A consulta acessa algo não permitido (somente SELECT nas tabelas do catálogo)."
                ) from exc
            raise
        return [dict(row) for row in fetched]
    finally:
        conn.close()
