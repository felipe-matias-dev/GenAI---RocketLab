import json
from typing import Callable, Optional

from app.cache import ResponseCache
from app.db import get_schema_description
from app.memory import SessionMemory
from app.tools import TOOL_SCHEMAS

SYSTEM_PROMPT_TEMPLATE = """\
Você é um assistente de dados da CineData Analytics. Responda perguntas em \
português (pt-BR) sobre o catálogo de filmes usando APENAS as ferramentas \
disponíveis para consultar o banco de dados. Nunca invente números.

Regras de negócio:
- "Receita", "Faturamento" e "Bilheteria" são sinônimos (coluna receita_usd/receita_brl).
- Você só pode LER dados (SELECT). Não tente alterar o banco de nenhuma forma.
- Use `semantic_search_synopses` para perguntas sobre enredo/tema/similaridade \
de história, e `execute_sql` para perguntas estruturadas/agregações.

Schema disponível:
{schema}
"""


class ModelUnavailable(Exception):
    """Erro de infraestrutura do provider (429/5xx) — deve escalar para o próximo modelo."""


class AllModelsFailedError(Exception):
    """Nenhum modelo da cadeia conseguiu responder a pergunta."""


CompleteFn = Callable[[str, list[dict], list[dict]], object]
ToolExecutor = Callable[[str, dict], dict]


class Orchestrator:
    def __init__(
        self,
        complete_fn: CompleteFn,
        tool_executor: ToolExecutor,
        memory: SessionMemory,
        cache: ResponseCache,
        model_chain: list[str],
        max_iterations: int,
    ):
        self._complete_fn = complete_fn
        self._tool_executor = tool_executor
        self._memory = memory
        self._cache = cache
        self._model_chain = model_chain
        self._max_iterations = max_iterations

    def ask(self, question: str, session_id: Optional[str] = None) -> dict:
        history = self._memory.get_history(session_id) if session_id else []

        if not history:
            cached = self._cache.get(question)
            if cached is not None:
                return cached

        messages = [{"role": "system", "content": self._system_prompt()}]
        messages.extend(history)
        messages.append({"role": "user", "content": question})

        result = self._run_model_chain(messages)

        if session_id:
            self._memory.add_turn(session_id, "user", question)
            self._memory.add_turn(session_id, "assistant", result["answer"])

        if not history:
            self._cache.set(question, result)

        return result

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(schema=get_schema_description())

    def _run_model_chain(self, messages: list[dict]) -> dict:
        for model in self._model_chain:
            try:
                result = self._run_with_model(model, list(messages))
            except ModelUnavailable:
                continue
            if result is not None:
                return result
        raise AllModelsFailedError(
            f"Nenhum modelo da cadeia {self._model_chain} conseguiu responder."
        )

    def _run_with_model(self, model: str, messages: list[dict]) -> Optional[dict]:
        sql_used: list[str] = []
        last_data = None

        for _ in range(self._max_iterations):
            response = self._complete_fn(model, messages, TOOL_SCHEMAS)
            message = response.choices[0].message

            if message.content and not message.tool_calls:
                return {
                    "answer": message.content,
                    "sql_used": sql_used,
                    "data": last_data,
                    "model_used": model,
                }

            if not message.tool_calls:
                # Resposta vazia (nem conteúdo, nem tool_calls) de um modelo
                # instável: não é uma resposta final válida, então tratamos
                # como uma iteração improdutiva em vez de "resolver" com nada.
                continue

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in message.tool_calls
                    ],
                }
            )

            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)
                result = self._tool_executor(tool_call.function.name, arguments)

                if tool_call.function.name == "execute_sql" and result.get("ok"):
                    sql_used.append(arguments.get("query", ""))
                    last_data = result.get("rows")

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return None
