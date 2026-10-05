"""Correção automática da avaliação: compara a saída do agente com um gabarito SQL.

O gabarito é uma query em `eval/reference_sql/<id>.sql` cujas colunas seguem a
convenção `key_*` (identificam a linha: título, nome, gênero) e `metric_*`
(valor numérico). Os nomes das colunas do agente não precisam coincidir — o
agente escolhe seus próprios aliases —, então a comparação é por valores:

- cada `key_*` do gabarito deve aparecer (sem diferenciar maiúsculas) em
  alguma célula de texto da linha do agente;
- cada `metric_*` deve aparecer em alguma célula numérica, com tolerância
  relativa de 1%. Também aceita o valor ×100 ou ÷100, porque a mesma margem
  pode ser expressa como fração ou como percentual.

Perguntas em que o topo do ranking tem empates (ex.: várias divergências
iguais a 10.0) usam `"use_keys": false` e conferem só as métricas.

Perguntas do agente híbrido (`"kind": "semantic"`) não têm gabarito SQL — o
"certo" é um conjunto aberto de filmes. A correção automática é um proxy de
precisão: o agente precisa ter chamado `semantic_search_synopses`, ao menos
`min_relevant` dos `top_k` primeiros filmes devolvidos precisam ter alguma
palavra-chave do tema na sinopse/título, e a resposta precisa citar ao menos
um desses filmes relevantes (senão a busca acertou, mas a resposta não a usou).
"""

import re
import unicodedata
from typing import Optional

REL_TOL = 0.01
ABS_TOL = 1e-6


def _split(row: dict) -> tuple[list, list]:
    keys = [v for k, v in row.items() if k.startswith("key_")]
    metrics = [v for k, v in row.items() if k.startswith("metric_")]
    return keys, metrics


def _numbers(row: dict) -> list[float]:
    return [
        float(v) for v in row.values() if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]


def _strings(row: dict) -> list[str]:
    return [str(v).casefold().strip() for v in row.values() if isinstance(v, str)]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(ABS_TOL, REL_TOL * abs(b))


def _metric_found(expected: float, numbers: list[float]) -> bool:
    candidates = (expected, expected * 100, expected / 100)
    return any(_close(n, c) for n in numbers for c in candidates)


def _row_matches(reference: dict, candidate: dict, use_keys: bool) -> bool:
    keys, metrics = _split(reference)
    strings, numbers = _strings(candidate), _numbers(candidate)
    if use_keys:
        for key in keys:
            if isinstance(key, str):
                if str(key).casefold().strip() not in strings:
                    return False
            elif key is not None and not _metric_found(float(key), numbers):
                return False  # chave numérica (ex.: ano)
    for metric in metrics:
        if metric is not None and not _metric_found(float(metric), numbers):
            return False
    return True


def _tie_group(row: dict, reference: list[dict]) -> list[dict]:
    """Linhas do gabarito com as mesmas métricas de `row` (inclui a própria)."""
    metrics = _split(row)[1]
    if not metrics:
        return [row]
    return [
        other
        for other in reference
        if len(_split(other)[1]) == len(metrics)
        and all(
            (a is None and b is None) or (a is not None and b is not None and _close(a, b))
            for a, b in zip(_split(other)[1], metrics)
        )
    ]


def grade_rows(reference: list[dict], data: Optional[list[dict]], check: dict) -> tuple[bool, str]:
    if not data:
        return False, "o agente não devolveu linhas de dados"
    use_keys = check.get("use_keys", True)
    ordered = check.get("ordered", True)

    if check.get("match", "prefix") == "all":
        if len(data) < len(reference):
            return False, f"esperadas {len(reference)} linhas, o agente devolveu {len(data)}"
        expected = reference
    else:
        # Ranking sem tamanho fixo: o agente pode devolver 1 ou N linhas; as
        # que devolver precisam ser o começo do gabarito.
        expected = reference[: min(len(reference), len(data))]

    if ordered:
        for index, ref in enumerate(expected):
            # Linhas empatadas na métrica podem vir em qualquer ordem — a
            # pergunta não define desempate —, então a chave pode ser a de
            # qualquer linha do mesmo grupo de empate.
            if not any(
                _row_matches(tied, data[index], use_keys) for tied in _tie_group(ref, reference)
            ):
                return False, f"linha {index + 1} difere do gabarito ({_describe(ref)})"
        return True, f"{len(expected)} linha(s) conferem, na ordem"

    remaining = list(data)
    for ref in expected:
        hit = next((row for row in remaining if _row_matches(ref, row, use_keys)), None)
        if hit is None:
            return False, f"linha do gabarito ausente ({_describe(ref)})"
        remaining.remove(hit)
    return True, f"{len(expected)} linha(s) conferem"


def _describe(row: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in row.items())


def grade_answer_number(reference: list[dict], answer: str) -> tuple[bool, str]:
    expected = int(next(iter(_split(reference[0])[1])))
    # "3.218", "3 218" e "3218" são o mesmo número escrito de formas diferentes.
    found = {int(re.sub(r"\D", "", m)) for m in re.findall(r"\d[\d.\s]*\d|\d", answer or "")}
    ok = expected in found
    return ok, f"esperado {expected} na resposta" + ("" if ok else f"; números achados: {sorted(found)}")


def _fold(text: str) -> str:
    """Minúsculas e sem acentos: "Máquina" e "maquina" são a mesma palavra-chave."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _keyword_pattern(keywords: list[str]) -> re.Pattern:
    # Palavra inteira com plural opcional: "robot" pega "robots", "paradox"
    # pega "paradoxes", mas "ai" não pega "aimed".
    alternatives = "|".join(re.escape(_fold(k)) for k in keywords)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?:s|es)?(?!\w)")


def grade_semantic(check: dict, result: dict) -> tuple[bool, str]:
    if "semantic_search_synopses" not in (result.get("tools_used") or []):
        return False, "não chamou semantic_search_synopses"

    seen, hits = set(), []
    for hit in result.get("semantic_hits") or []:
        title = hit.get("titulo") or ""
        if title and title not in seen:
            seen.add(title)
            hits.append(hit)
    top_k = check.get("top_k", 5)
    hits = hits[:top_k]
    if not hits:
        return False, "a busca semântica não devolveu filmes"

    pattern = _keyword_pattern(check["keywords"])
    relevant = [
        h["titulo"] for h in hits if pattern.search(_fold(f"{h['titulo']} {h.get('sinopse') or ''}"))
    ]
    answer = _fold(result.get("answer", ""))
    cited = [title for title in relevant if _fold(title) in answer]

    min_relevant = check.get("min_relevant", 3)
    ok = len(relevant) >= min_relevant and len(cited) >= 1
    detail = (
        f"{len(relevant)}/{len(hits)} sinopses no tema (mínimo {min_relevant}); "
        f"resposta cita {len(cited)} delas"
    )
    return ok, detail


def grade(check: dict, reference: Optional[list[dict]], result: dict) -> dict:
    """Devolve {"verdict": PASS|FAIL|MANUAL, "detail": str} para uma pergunta."""
    kind = check.get("kind", "manual")
    sql_used = result.get("sql_used") or []

    if kind == "manual":
        return {"verdict": "MANUAL", "detail": check.get("note", "sem checagem automática")}

    if kind == "refusal":
        confidence = result.get("confidence")
        ok = not sql_used and (confidence is None or confidence <= 0.2)
        return {
            "verdict": "PASS" if ok else "FAIL",
            "detail": f"SQL executado: {len(sql_used)}; confiança: {confidence}",
        }

    if kind == "explain":
        ok = any(q.lstrip().upper().startswith("EXPLAIN") for q in sql_used)
        return {"verdict": "PASS" if ok else "FAIL", "detail": "usou EXPLAIN" if ok else "não usou EXPLAIN"}

    if kind == "semantic":
        ok, detail = grade_semantic(check, result)
        return {"verdict": "PASS" if ok else "FAIL", "detail": detail}

    if reference is None:
        return {"verdict": "FAIL", "detail": "gabarito não pôde ser executado"}

    if kind == "answer_number":
        ok, detail = grade_answer_number(reference, result.get("answer", ""))
    elif kind == "rows":
        ok, detail = grade_rows(reference, result.get("data"), check)
    else:
        raise ValueError(f"tipo de checagem desconhecido: {kind}")
    return {"verdict": "PASS" if ok else "FAIL", "detail": detail}
