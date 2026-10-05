"""Roda o conjunto de perguntas de eval/questions.json contra o agente real e
gera eval/results.md.

Atenção: cada pergunta nova consome pelo menos 1 requisição da cota diária
do OpenRouter (50/dia no free tier). Perguntas repetidas entre execuções são
resolvidas pelo cache (app/cache.py) sem gastar cota. Rode com moderação —
não é parte da suíte automática (pytest).

Uso:
    python -m eval.run_eval                       # todas as perguntas
    python -m eval.run_eval --ids fin-01 pop-01   # só algumas (acumula em results.json)
    python -m eval.run_eval --stop-after 2        # para após 2 falhas totais seguidas

Os resultados são acumulados por id em eval/results.json e o results.md é
regerado a cada pergunta — assim a avaliação pode ser feita em etapas ao longo
de dias (cota de 50/dia) sem perder o que já foi medido.
"""

import argparse
import json
import time
from pathlib import Path

from app import llm
from app.db import run_query
from app.factory import build_orchestrator
from app.orchestrator import AllModelsFailedError
from eval.grading import grade

REFERENCE_DIR = Path(__file__).parent / "reference_sql"
REFERENCE_TIMEOUT_SECONDS = 60


def load_reference(question_id: str) -> list[dict] | None:
    """Executa o gabarito SQL da pergunta; None se não houver arquivo ou se falhar."""
    path = REFERENCE_DIR / f"{question_id}.sql"
    if not path.exists():
        return None
    try:
        return run_query(path.read_text(encoding="utf-8"), timeout_seconds=REFERENCE_TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - gabarito quebrado vira FAIL, não derruba a avaliação
        print(f"  (gabarito de {question_id} falhou: {exc})")
        return None

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_PATH = Path(__file__).parent / "results.md"
RESULTS_JSON_PATH = Path(__file__).parent / "results.json"


def _load_previous() -> dict[str, dict]:
    if not RESULTS_JSON_PATH.exists():
        return {}
    return {row["id"]: row for row in json.loads(RESULTS_JSON_PATH.read_text(encoding="utf-8"))}


def _persist(by_id: dict[str, dict], order: list[str]) -> None:
    rows = [by_id[qid] for qid in order if qid in by_id]
    RESULTS_JSON_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(rows)


def run(ids: list[str] | None = None, stop_after: int | None = None) -> None:
    all_questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    order = [q["id"] for q in all_questions]
    questions = [q for q in all_questions if ids is None or q["id"] in ids]
    orchestrator = build_orchestrator()

    by_id = _load_previous()
    consecutive_failures = 0
    for item in questions:
        start = time.monotonic()
        calls_before = llm.call_count
        result = None
        try:
            result = orchestrator.ask(item["question"])
            answer = result["answer"]
            model_used = result["model_used"]
            sql_used = " | ".join(result["sql_used"]) or "-"
            confidence = result.get("confidence")
            reasoning = result.get("reasoning")
            schema_link = result.get("schema_link")
            error = None
        except AllModelsFailedError as exc:
            answer, model_used, sql_used = "-", "-", "-"
            confidence, reasoning, schema_link = None, None, None
            error = str(exc)
        elapsed = time.monotonic() - start
        llm_calls = llm.call_count - calls_before
        if error:
            grading = {"verdict": "FAIL", "detail": error}
        else:
            grading = grade(item.get("check", {}), load_reference(item["id"]), result)

        by_id[item["id"]] = (
            {
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "expected_shape": item["expected_shape"],
                "answer": answer,
                "model_used": model_used,
                "sql_used": sql_used,
                "confidence": confidence,
                "reasoning": reasoning,
                "schema_link": schema_link,
                "elapsed_s": round(elapsed, 1),
                "llm_calls": llm_calls,
                "verdict": grading["verdict"],
                "verdict_detail": grading["detail"],
                "error": error,
            }
        )
        print(f"[{item['id']}] {elapsed:.1f}s — {model_used} — {grading['verdict']} ({llm_calls} chamadas) — {grading['detail']}")

        _persist(by_id, order)

        consecutive_failures = consecutive_failures + 1 if error else 0
        if stop_after and consecutive_failures >= stop_after:
            print(f"\nParando: {consecutive_failures} falhas totais seguidas (cota esgotada?).")
            break

    print(f"\nRelatório escrito em {RESULTS_PATH}")


def _write_report(rows: list[dict]) -> None:
    lines = ["# Resultado da avaliação\n", _summary(rows), ""]
    for row in rows:
        lines.append(f"## {row['id']} — {row['category']}")
        lines.append(f"**Pergunta:** {row['question']}\n")
        lines.append(f"**Esperado (forma):** {row['expected_shape']}\n")
        lines.append(f"**Veredito automático:** {row['verdict']} — {row['verdict_detail']}\n")
        lines.append(f"**Chamadas ao LLM:** {row['llm_calls']}\n")
        if row["error"]:
            lines.append(f"**Erro:** {row['error']}\n")
        else:
            lines.append(f"**Resposta do agente:** {row['answer']}\n")
            lines.append(f"**SQL usada:** `{row['sql_used']}`\n")
            lines.append(f"**Modelo:** {row['model_used']} · **Tempo:** {row['elapsed_s']}s\n")
            confidence = row.get("confidence")
            confidence_text = f"{confidence:.0%}" if confidence is not None else "n/d"
            lines.append(f"**Confiança:** {confidence_text}\n")
            lines.append(f"**Raciocínio:** {row.get('reasoning') or 'n/d'}\n")
            lines.append(f"**Schema linking:** {_format_schema_link(row.get('schema_link'))}\n")
        lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


def _summary(rows: list[dict]) -> str:
    counts = {v: sum(r["verdict"] == v for r in rows) for v in ("PASS", "FAIL", "MANUAL")}
    graded = counts["PASS"] + counts["FAIL"]
    total_calls = sum(r["llm_calls"] for r in rows)
    lines = [
        f"**Acertos automáticos: {counts['PASS']}/{graded}** "
        f"({counts['MANUAL']} pergunta(s) para revisão manual) · "
        f"**{total_calls} chamadas ao LLM** nas {len(rows)} perguntas "
        f"({total_calls / max(len(rows), 1):.1f} por pergunta)\n",
        "| Pergunta | Veredito | Chamadas | Detalhe |",
        "|---|---|---|---|",
    ]
    for r in rows:
        detail = r["verdict_detail"].replace("|", "/")
        lines.append(f"| {r['id']} | {r['verdict']} | {r['llm_calls']} | {detail} |")
    return "\n".join(lines)


def _format_schema_link(schema_link: dict | None) -> str:
    """Formata schema_link como texto legível, em vez do repr bruto do dict
    Python (que exporia sintaxe de dict no relatório .md)."""
    if not schema_link:
        return "n/d"
    tables = ", ".join(schema_link.get("tables") or []) or "(nenhuma)"
    columns = ", ".join(schema_link.get("columns") or []) or "(nenhuma)"
    reasoning = schema_link.get("reasoning") or "n/d"
    return f"tabelas: {tables}; colunas: {columns}; raciocínio: {reasoning}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Avalia o agente contra eval/questions.json")
    parser.add_argument("--ids", nargs="+", help="ids das perguntas a rodar (padrão: todas)")
    parser.add_argument("--stop-after", type=int, help="para após N falhas totais seguidas")
    args = parser.parse_args()
    run(ids=args.ids, stop_after=args.stop_after)
