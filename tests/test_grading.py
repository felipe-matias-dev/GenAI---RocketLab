import json
from pathlib import Path

import pytest

from app.db import run_query
from eval import run_eval
from eval.grading import grade, grade_answer_number, grade_rows

REFERENCE = [
    {"key_titulo": "Avatar", "metric_receita": 100.0},
    {"key_titulo": "Titanic", "metric_receita": 80.0},
]


def test_rows_pass_when_values_match_regardless_of_column_names():
    data = [
        {"filme": "avatar", "receita_brl": 100.0, "ano": 2009},
        {"filme": "Titanic", "receita_brl": 80.4, "ano": 1997},
    ]
    ok, _ = grade_rows(REFERENCE, data, {"kind": "rows"})
    assert ok


def test_rows_fail_on_wrong_order_when_ordered():
    data = [{"t": "Titanic", "r": 80.0}, {"t": "Avatar", "r": 100.0}]
    ok, detail = grade_rows(REFERENCE, data, {"kind": "rows"})
    assert not ok and "linha 1" in detail


def test_rows_accept_any_order_when_unordered():
    data = [{"t": "Titanic", "r": 80.0}, {"t": "Avatar", "r": 100.0}]
    ok, _ = grade_rows(REFERENCE, data, {"kind": "rows", "ordered": False})
    assert ok


def test_rows_fail_on_wrong_metric():
    data = [{"t": "Avatar", "r": 55.0}, {"t": "Titanic", "r": 80.0}]
    ok, _ = grade_rows(REFERENCE, data, {"kind": "rows"})
    assert not ok


def test_metric_accepts_fraction_vs_percent_scale():
    reference = [{"key_titulo": "X", "metric_margem": 99.9}]
    ok, _ = grade_rows(reference, [{"t": "X", "m": 0.999}], {"kind": "rows"})
    assert ok


def test_prefix_match_accepts_fewer_rows_than_reference():
    ok, _ = grade_rows(REFERENCE, [{"t": "Avatar", "r": 100.0}], {"kind": "rows"})
    assert ok


def test_match_all_requires_every_reference_row():
    ok, detail = grade_rows(REFERENCE, [{"t": "Avatar", "r": 100.0}], {"match": "all"})
    assert not ok and "esperadas 2" in detail


def test_use_keys_false_ignores_tied_titles():
    reference = [{"key_titulo": "A", "metric_divergencia": 10.0}]
    ok, _ = grade_rows(reference, [{"t": "Outro filme empatado", "d": 10.0}], {"use_keys": False})
    assert ok


def test_no_data_fails():
    assert grade_rows(REFERENCE, None, {})[0] is False
    assert grade_rows(REFERENCE, [], {})[0] is False


@pytest.mark.parametrize("answer", ["Há 3218 filmes.", "São 3.218 filmes de ficção.", "3 218 filmes"])
def test_answer_number_accepts_common_formats(answer):
    ok, _ = grade_answer_number([{"metric_filmes": 3218}], answer)
    assert ok


def test_answer_number_rejects_wrong_count():
    ok, detail = grade_answer_number([{"metric_filmes": 3218}], "Existem 120 filmes.")
    assert not ok and "3218" in detail


def test_refusal_passes_without_sql_and_low_confidence():
    result = {"sql_used": [], "confidence": 0.0, "answer": "não posso"}
    assert grade({"kind": "refusal"}, None, result)["verdict"] == "PASS"


def test_refusal_fails_when_sql_was_executed():
    result = {"sql_used": ["SELECT 1"], "confidence": 0.0, "answer": "x"}
    assert grade({"kind": "refusal"}, None, result)["verdict"] == "FAIL"


def test_explain_requires_explain_prefix():
    assert grade({"kind": "explain"}, None, {"sql_used": ["EXPLAIN QUERY PLAN SELECT 1"]})["verdict"] == "PASS"
    assert grade({"kind": "explain"}, None, {"sql_used": ["SELECT 1"]})["verdict"] == "FAIL"


def test_manual_checks_are_not_scored():
    assert grade({"kind": "manual"}, None, {})["verdict"] == "MANUAL"


def test_missing_reference_is_a_failure_not_a_crash():
    assert grade({"kind": "rows"}, None, {"data": [{"a": 1}]})["verdict"] == "FAIL"


# --- gabaritos ------------------------------------------------------------

QUESTIONS = json.loads((Path(run_eval.__file__).parent / "questions.json").read_text(encoding="utf-8"))


def test_every_question_declares_a_check():
    assert all("check" in q for q in QUESTIONS)


@pytest.mark.parametrize("question", [q for q in QUESTIONS if q["check"]["kind"] in ("rows", "answer_number")])
def test_reference_sql_exists_and_compiles_against_real_schema(question):
    path = run_eval.REFERENCE_DIR / f"{question['id']}.sql"
    assert path.exists(), f"falta o gabarito {path.name}"
    # EXPLAIN QUERY PLAN valida colunas/tabelas sem pagar a execução completa.
    run_query("EXPLAIN QUERY PLAN " + path.read_text(encoding="utf-8"), timeout_seconds=10)


def test_reference_columns_follow_key_metric_convention():
    for path in run_eval.REFERENCE_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        assert "AS key_" in text or "AS metric_" in text, path.name


def test_ordered_match_tolerates_tied_metrics_in_any_order():
    reference = [
        {"key_diretor": "A", "metric_nota": 9.5},
        {"key_diretor": "B", "metric_nota": 9.1875},
        {"key_diretor": "C", "metric_nota": 9.1875},
        {"key_diretor": "D", "metric_nota": 9.0},
    ]
    data = [
        {"n": "A", "m": 9.5},
        {"n": "C", "m": 9.1875},  # B e C empatam: a ordem entre eles é arbitrária
        {"n": "B", "m": 9.1875},
        {"n": "D", "m": 9.0},
    ]
    assert grade_rows(reference, data, {"kind": "rows"})[0]


def test_tie_tolerance_does_not_hide_a_wrong_key_outside_the_tie_group():
    reference = [
        {"key_diretor": "A", "metric_nota": 9.5},
        {"key_diretor": "B", "metric_nota": 9.1875},
        {"key_diretor": "C", "metric_nota": 9.1875},
    ]
    data = [{"n": "A", "m": 9.5}, {"n": "Z", "m": 9.1875}, {"n": "C", "m": 9.1875}]
    assert not grade_rows(reference, data, {"kind": "rows"})[0]


# --- agente híbrido (busca semântica) ---------------------------------------

SEMANTIC_CHECK = {
    "kind": "semantic",
    "top_k": 3,
    "min_relevant": 2,
    "keywords": ["time travel", "time machine", "paradox", "maquina do tempo", "ai"],
}


def _semantic_result(hits, answer, tools=("semantic_search_synopses",)):
    return {
        "tools_used": list(tools),
        "semantic_hits": [{"titulo": t, "sinopse": s} for t, s in hits],
        "answer": answer,
    }


def test_semantic_passes_when_hits_are_on_topic_and_cited():
    result = _semantic_result(
        [("Loop", "A man uses a time machine."), ("Klatos", "A paradox destroys the universe."), ("Mahmood", "Music.")],
        "Recomendo Loop e Klatos.",
    )
    verdict = grade(SEMANTIC_CHECK, None, result)
    assert verdict["verdict"] == "PASS"
    assert verdict["detail"].startswith("2/3")


def test_semantic_fails_without_calling_the_semantic_tool():
    result = _semantic_result([("Loop", "time machine")], "Loop", tools=("execute_sql",))
    assert grade(SEMANTIC_CHECK, None, result)["verdict"] == "FAIL"


def test_semantic_fails_when_retrieval_is_off_topic():
    # Caso real medido: consulta em português contra sinopses em inglês trouxe
    # documentários musicais para "viagem no tempo".
    result = _semantic_result(
        [("Beyond Noh", "Animated masks."), ("9 Fugas", "An orchestra improvises."), ("Loop", "time machine")],
        "Beyond Noh, 9 Fugas e Loop.",
    )
    assert grade(SEMANTIC_CHECK, None, result)["verdict"] == "FAIL"


def test_semantic_fails_when_answer_ignores_the_relevant_hits():
    result = _semantic_result(
        [("Loop", "time machine"), ("Klatos", "paradox")],
        "Não encontrei filmes sobre o tema.",
    )
    assert grade(SEMANTIC_CHECK, None, result)["verdict"] == "FAIL"


def test_semantic_keywords_ignore_accents_and_match_plurals_only_as_whole_words():
    on_topic = _semantic_result(
        [("A", "Uma MÁQUINA DO TEMPO quebrada."), ("B", "Two paradoxes collide."), ("C", "AI wakes up.")],
        "A, B e C.",
    )
    assert grade(SEMANTIC_CHECK, None, on_topic)["detail"].startswith("3/3")

    # "ai" não pode casar com "aimed" nem "paradox" com "paradoxical".
    off_topic = _semantic_result([("A", "aimed high"), ("B", "a paradoxical man")], "A e B.")
    assert grade(SEMANTIC_CHECK, None, off_topic)["detail"].startswith("0/2")


def test_semantic_deduplicates_repeated_searches_before_cutting_top_k():
    result = _semantic_result(
        [("Loop", "time machine"), ("Loop", "time machine"), ("Klatos", "paradox"), ("Z", "x")],
        "Loop e Klatos.",
    )
    assert grade(SEMANTIC_CHECK, None, result)["detail"].startswith("2/3")


def test_hybrid_questions_are_graded_automatically():
    hybrid = [q for q in QUESTIONS if q["id"].startswith("hybrid")]
    assert hybrid and all(q["check"]["kind"] == "semantic" for q in hybrid)
