"""REPL interativo para rodar perguntas direto contra o agente, sem subir o
servidor HTTP. Reaproveita app.factory.build_orchestrator — a mesma fiação
de produção usada por app/main.py e eval/run_eval.py.

Uso:
    python -m app.cli
"""

from app.factory import build_orchestrator
from app.orchestrator import AllModelsFailedError

_EXIT_COMMANDS = {"sair", "exit", "quit"}
_SESSION_ID = "cli"


def cli_main() -> None:
    orchestrator = build_orchestrator()
    print("CineData Analytics — CLI (digite 'sair' para encerrar)\n")

    while True:
        try:
            question = input("> ").strip()
        except EOFError:
            break

        if not question:
            continue
        if question.lower() in _EXIT_COMMANDS:
            break

        try:
            result = orchestrator.ask(question, session_id=_SESSION_ID)
        except AllModelsFailedError as exc:
            print(f"Erro: {exc}\n")
            continue

        _print_result(result)


def _print_result(result: dict) -> None:
    print(result["answer"])

    confidence = result.get("confidence")
    confidence_text = f"{confidence:.0%} ({confidence})" if confidence is not None else "n/d"
    print(f"Modelo: {result['model_used']} · Confiança: {confidence_text}")

    if result.get("sql_used"):
        print(f"SQL: {' | '.join(result['sql_used'])}")
    if result.get("reasoning"):
        print(f"Raciocínio: {result['reasoning']}")
    print()


if __name__ == "__main__":
    cli_main()
