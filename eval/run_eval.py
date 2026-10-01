"""Roda o conjunto de perguntas de eval/questions.json contra o agente real e
gera eval/results.md.

Atenção: cada pergunta nova consome pelo menos 1 requisição da cota diária
do OpenRouter (50/dia no free tier). Perguntas repetidas entre execuções são
resolvidas pelo cache (app/cache.py) sem gastar cota. Rode com moderação —
não é parte da suíte automática (pytest).

Uso:
    python -m eval.run_eval
"""

import json
import time
from pathlib import Path

from app.factory import build_orchestrator
from app.orchestrator import AllModelsFailedError

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_PATH = Path(__file__).parent / "results.md"


def run() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    orchestrator = build_orchestrator()

    rows = []
    for item in questions:
        start = time.monotonic()
        try:
            result = orchestrator.ask(item["question"])
            answer = result["answer"]
            model_used = result["model_used"]
            sql_used = " | ".join(result["sql_used"]) or "-"
            error = None
        except AllModelsFailedError as exc:
            answer, model_used, sql_used = "-", "-", "-"
            error = str(exc)
        elapsed = time.monotonic() - start

        rows.append(
            {
                "id": item["id"],
                "category": item["category"],
                "question": item["question"],
                "expected_shape": item["expected_shape"],
                "answer": answer,
                "model_used": model_used,
                "sql_used": sql_used,
                "elapsed_s": round(elapsed, 1),
                "error": error,
            }
        )
        print(f"[{item['id']}] {elapsed:.1f}s — {model_used} — {'ERRO: ' + error if error else 'ok'}")

    _write_report(rows)
    print(f"\nRelatório escrito em {RESULTS_PATH}")


def _write_report(rows: list[dict]) -> None:
    lines = ["# Resultado da avaliação\n"]
    for row in rows:
        lines.append(f"## {row['id']} — {row['category']}")
        lines.append(f"**Pergunta:** {row['question']}\n")
        lines.append(f"**Esperado (forma):** {row['expected_shape']}\n")
        if row["error"]:
            lines.append(f"**Erro:** {row['error']}\n")
        else:
            lines.append(f"**Resposta do agente:** {row['answer']}\n")
            lines.append(f"**SQL usada:** `{row['sql_used']}`\n")
            lines.append(f"**Modelo:** {row['model_used']} · **Tempo:** {row['elapsed_s']}s\n")
        lines.append("")

    RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()
