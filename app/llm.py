import openai
from openai import OpenAI

from app.config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    LLM_REQUEST_TIMEOUT_SECONDS,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)
from app.orchestrator import ModelUnavailable

# APITimeoutError é subclasse de APIConnectionError, então já cai aqui:
# um timeout (ver LLM_REQUEST_TIMEOUT_SECONDS) escala para o próximo modelo
# da cadeia como qualquer outro erro de infraestrutura.
#
# NotFoundError (404) entra aqui porque modelos ":free" somem ou passam a ser
# pagos sem aviso ("This model is unavailable for free") — sem isso, um modelo
# aposentado no meio da cadeia derrubava a pergunta em vez de escalar.
_INFRA_ERRORS = (
    openai.RateLimitError,
    openai.InternalServerError,
    openai.APIConnectionError,
    openai.NotFoundError,
)

# 413 (Request Entity Too Large) é o Groq recusando uma requisição grande
# demais — o plano gratuito do gpt-oss-120b aceita 8K tokens/minuto, e o
# prompt com schema + resultados de tools cresce a cada iteração. Repetir não
# resolve (o tamanho é o mesmo), mas outro modelo da cadeia pode aceitar.
_INFRA_STATUS_CODES = {413}

# 400 do Groq rejeitando uma geração do próprio modelo que não virou tool call
# válida. Visto com gpt-oss-120b nas duas formas: "output_parse_failed" (o
# modelo escreveu "...Use finalize_answer." como texto) e "tool_use_failed"
# (chamou uma tool inexistente, "<|channel|>commentary", com os argumentos
# certos de finalize_answer). É aleatório: a mesma requisição costuma passar na
# tentativa seguinte. Sem tratamento, o BadRequestError subia como 500 na API.
_RETRYABLE_GENERATION_CODES = {"output_parse_failed", "tool_use_failed"}
MAX_GENERATION_RETRIES = 2

DEFAULT_PROVIDER = "openrouter"
PROVIDERS = ("openrouter", "groq")


# Total de chamadas feitas ao provider neste processo (inclui as que falham).
# Cada uma consome cota do OpenRouter; a avaliação usa o delta por pergunta.
call_count = 0


def split_model(model: str) -> tuple[str, str]:
    """Separa "groq:openai/gpt-oss-120b" em ("groq", "openai/gpt-oss-120b").

    Sem prefixo conhecido, o modelo é do OpenRouter — os ids do OpenRouter têm
    "/" e ":free", mas nunca começam com o nome de um provedor seguido de ":".
    """
    prefix, sep, rest = model.partition(":")
    if sep and prefix in PROVIDERS and rest:
        return prefix, rest
    return DEFAULT_PROVIDER, model


def get_client(api_key: str = OPENROUTER_API_KEY) -> OpenAI:
    """Cliente OpenAI-compatível apontado para o OpenRouter."""
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )


def get_groq_client(api_key: str = GROQ_API_KEY) -> OpenAI:
    """Cliente OpenAI-compatível apontado para o Groq (provedor reserva)."""
    return OpenAI(
        api_key=api_key,
        base_url=GROQ_BASE_URL,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )


def _error_code(exc: openai.APIStatusError) -> str | None:
    code = getattr(exc, "code", None)
    if code is None and isinstance(exc.body, dict):
        code = exc.body.get("code") or (exc.body.get("error") or {}).get("code")
    return code


def complete(client: OpenAI, model: str, messages: list[dict], tools: list[dict]):
    """Chama o modelo e converte erros de infraestrutura (429/413/5xx/conexão) em
    ModelUnavailable, para que o orchestrator escale para o próximo modelo da
    cadeia. Uma geração malformada (output_parse_failed) é repetida até
    MAX_GENERATION_RETRIES vezes antes de escalar. Outros erros (ex.: 401 de
    chave inválida) propagam sem conversão, já que trocar de modelo gratuito
    não resolveria."""
    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    global call_count
    for attempt in range(MAX_GENERATION_RETRIES + 1):
        call_count += 1
        try:
            return client.chat.completions.create(**kwargs)
        except _INFRA_ERRORS as exc:
            raise ModelUnavailable(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code in _INFRA_STATUS_CODES:
                raise ModelUnavailable(str(exc)) from exc
            if _error_code(exc) in _RETRYABLE_GENERATION_CODES:
                if attempt < MAX_GENERATION_RETRIES:
                    continue
                raise ModelUnavailable(str(exc)) from exc
            raise


def complete_routed(clients: dict[str, OpenAI], model: str, messages: list[dict], tools: list[dict]):
    """Como `complete`, mas escolhe o cliente pelo prefixo do modelo na cadeia.

    Um provedor sem cliente (ex.: "groq:..." em OPENROUTER_MODELS sem
    GROQ_API_KEY) vira ModelUnavailable: a cadeia segue para o próximo modelo
    em vez de a pergunta morrer num KeyError.
    """
    provider, model_id = split_model(model)
    client = clients.get(provider)
    if client is None:
        raise ModelUnavailable(f"provedor '{provider}' sem chave configurada")
    return complete(client, model_id, messages, tools)
