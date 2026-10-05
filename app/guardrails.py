import re

DEFAULT_ROW_LIMIT = 500

# EXPLAIN/EXPLAIN QUERY PLAN são prefixos de leitura (inspecionam o plano de
# execução, nunca escrevem) — aceitos como prefixo opcional antes de
# SELECT/WITH. Não precisa de tratamento especial no LIMIT abaixo: tanto
# "EXPLAIN SELECT ... LIMIT N" quanto "EXPLAIN QUERY PLAN SELECT ... LIMIT N"
# são SQL válido no SQLite.
_ALLOWED_START = re.compile(
    r"^\s*(EXPLAIN\s+QUERY\s+PLAN\s+|EXPLAIN\s+)?(SELECT|WITH)\b", re.IGNORECASE
)

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


def _scan(sql: str) -> tuple[str, str]:
    """Percorre `sql` uma vez e devolve duas visões do texto.

    - `code`: sem comentários e com literais/identificadores entre aspas
      esvaziados — é onde se procuram palavras proibidas, `;` e LIMIT, para
      que um título como 'Create' ou um ';' dentro de uma string não gerem
      falso positivo, nem um 'LIMIT' dentro de string gere falso negativo.
    - `text`: sem comentários, mas com os literais intactos — é o que
      realmente executa (e onde se anexa o LIMIT, já que um `--` final
      engoliria um LIMIT acrescentado ao texto original).
    """
    code: list[str] = []
    text: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            code.append(" ")
            text.append(" ")
            continue
        if ch in ("'", '"', "`"):
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:  # aspa escapada por duplicação
                        j += 2
                        continue
                    break
                j += 1
            else:
                raise GuardrailViolation("Literal ou identificador entre aspas não fechado.")
            text.append(sql[i : j + 1])
            code.append(ch + ch)
            i = j + 1
            continue
        code.append(ch)
        text.append(ch)
        i += 1
    return "".join(code), "".join(text)


def _has_top_level_limit(code: str) -> bool:
    """True se há um LIMIT fora de qualquer parêntese (limita o resultado final).

    Um LIMIT dentro de subquery/CTE não restringe o que o SELECT externo
    devolve — um JOIN entre duas subqueries limitadas ainda gera o produto.
    """
    depth = 0
    for match in re.finditer(r"[()]|\bLIMIT\b", code, re.IGNORECASE):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0:
            return True
    return False


def validate_sql(sql: str, row_limit: int = DEFAULT_ROW_LIMIT) -> str:
    """Valida que `sql` é uma única query de leitura e garante um LIMIT externo.

    Levanta GuardrailViolation para qualquer coisa que não seja um único
    SELECT/WITH sem palavras-chave de escrita/DDL. A conexão SQLite em
    db.py também é aberta em modo somente-leitura e `run_query` aplica um
    authorizer, como camadas adicionais de proteção.
    """
    if not sql.strip():
        raise GuardrailViolation("Query vazia.")

    code, text = _scan(sql)
    code, text = code.strip(), text.strip()
    if not code:
        raise GuardrailViolation("Query vazia.")

    # Permite no máximo um ';' final (statement único).
    if code.endswith(";"):
        code, text = code[:-1].rstrip(), text[:-1].rstrip()
    if ";" in code:
        raise GuardrailViolation("Apenas uma única instrução SQL é permitida.")

    if not _ALLOWED_START.match(code):
        raise GuardrailViolation("Apenas consultas SELECT/WITH são permitidas.")

    match = _FORBIDDEN_RE.search(code)
    if match:
        raise GuardrailViolation(
            f"Palavra-chave não permitida na query: {match.group(0).upper()}"
        )

    if not _has_top_level_limit(code):
        text = f"{text} LIMIT {row_limit}"

    return text
