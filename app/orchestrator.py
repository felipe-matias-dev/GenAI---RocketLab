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
- Se a pergunta for sobre performance ou plano de execução de uma consulta, \
prefixe a query passada a `execute_sql` com `EXPLAIN` ou `EXPLAIN QUERY PLAN` \
em vez de `SELECT`/`WITH` diretamente.
- Antes de filtrar por uma coluna de texto livre (nome de gênero, diretor, \
ator ou produtora) em uma cláusula WHERE, chame `get_distinct_values` para \
confirmar a grafia exata usada no banco — o valor que o usuário mencionou \
pode não corresponder exatamente (ex.: "Sci-Fi" vs "Science Fiction").

Para concluir sua resposta:
- Você DEVE sempre chamar a tool `finalize_answer` para encerrar o turno, \
nunca responda em texto livre sem chamá-la. Informe `answer` (resposta em \
pt-BR), `confidence` (0.0 a 1.0, sua confiança real na resposta) e \
`reasoning` (raciocínio resumido que levou a essa resposta).

Schema disponível:
{schema}
"""


class ModelUnavailable(Exception):
    """Erro de infraestrutura do provider (429/5xx) — deve escalar para o próximo modelo."""


class AllModelsFailedError(Exception):
    """Nenhum modelo da cadeia conseguiu responder a pergunta."""


CompleteFn = Callable[[str, list[dict], list[dict]], object]
ToolExecutor = Callable[[str, dict], dict]


def _coerce_confidence(value) -> Optional[float]:
    """Converte `value` em float clampado a [0.0, 1.0]; None se não for numérico.

    Defesa contra modelos gratuitos instáveis que podem mandar uma string,
    None, ou um número fora da faixa esperada no campo `confidence` de
    `finalize_answer`.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, number))


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
                # Caminho legado: fallback defensivo para um modelo que
                # ignore a instrução de sempre chamar finalize_answer.
                return {
                    "answer": message.content,
                    "sql_used": sql_used,
                    "data": last_data,
                    "model_used": model,
                    "confidence": None,
                    "reasoning": None,
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

            finalize_result = None

            for tool_call in message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)

                if tool_call.function.name == "finalize_answer":
                    # Terminal: não passa pelo tool_executor nem gera
                    # mensagem role:tool — o loop termina já nesta iteração.
                    finalize_result = {
                        "answer": arguments.get("answer", ""),
                        "confidence": _coerce_confidence(arguments.get("confidence")),
                        "reasoning": arguments.get("reasoning", ""),
                    }
                    continue

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

            if finalize_result is not None:
                return {
                    "sql_used": sql_used,
                    "data": last_data,
                    "model_used": model,
                    **finalize_result,
                }

        return None
