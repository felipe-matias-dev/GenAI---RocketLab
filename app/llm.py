import openai
from openai import OpenAI

from app.config import LLM_REQUEST_TIMEOUT_SECONDS, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from app.orchestrator import ModelUnavailable

# APITimeoutError é subclasse de APIConnectionError, então já cai aqui:
# um timeout (ver LLM_REQUEST_TIMEOUT_SECONDS) escala para o próximo modelo
# da cadeia como qualquer outro erro de infraestrutura.
_INFRA_ERRORS = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError)


def get_client(api_key: str = OPENROUTER_API_KEY) -> OpenAI:
    """Cliente OpenAI-compatível apontado para o OpenRouter."""
    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
    )


def complete(client: OpenAI, model: str, messages: list[dict], tools: list[dict]):
    """Chama o modelo e converte erros de infraestrutura (429/5xx/conexão) em
    ModelUnavailable, para que o orchestrator escale para o próximo modelo da
    cadeia. Outros erros (ex.: 401 de chave inválida) propagam sem conversão,
    já que trocar de modelo gratuito não resolveria."""
    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
    try:
        return client.chat.completions.create(**kwargs)
    except _INFRA_ERRORS as exc:
        raise ModelUnavailable(str(exc)) from exc
