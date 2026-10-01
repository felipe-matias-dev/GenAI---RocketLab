import re

DEFAULT_ROW_LIMIT = 500

_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)

_FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "VACUUM",
    "CREATE",
    "TRUNCATE",
]
# "REPLACE" é deliberadamente omitido: SQLite tem uma função escalar de leitura
# REPLACE(x, y, z), e a forma de escrita ("REPLACE INTO"/"INSERT OR REPLACE")
# já é bloqueada pelo _ALLOWED_START (toda query precisa começar com SELECT/WITH).
_FORBIDDEN_RE = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)


class GuardrailViolation(Exception):
    """Levantada quando uma query gerada pelo LLM viola as regras de acesso somente-leitura."""


def validate_sql(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Valida que `sql` é uma única query de leitura e garante um LIMIT.

    Levanta GuardrailViolation para qualquer coisa que não seja um único
    SELECT/WITH sem palavras-chave de escrita/DDL. A conexão SQLite em
    db.py também é aberta em modo somente-leitura como segunda camada de
    proteção.
    """
    cleaned = sql.strip()
    if not cleaned:
        raise GuardrailViolation("Query vazia.")

    # Permite no máximo um ';' final (statement único).
    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        raise GuardrailViolation("Apenas uma única instrução SQL é permitida.")

    if not _ALLOWED_START.match(body):
        raise GuardrailViolation("Apenas consultas SELECT/WITH são permitidas.")

    match = _FORBIDDEN_RE.search(body)
    if match:
        raise GuardrailViolation(
            f"Palavra-chave não permitida na query: {match.group(0).upper()}"
        )

    if not _LIMIT_RE.search(body):
        body = f"{body} LIMIT {row_limit}"

    return body
