import openai
from openai import OpenAI

from app.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from app.orchestrator import ModelUnavailable

_INFRA_ERRORS = (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError)


def get_client(api_key: str = OPENROUTER_API_KEY) -> OpenAI:
    """Cliente OpenAI-compatível apontado para o OpenRouter."""
    return OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)


def complete(client: OpenAI, model: str, messages: list[dict], tools: list[dict]):
    """Chama o modelo e converte erros de infraestrutura (429/5xx/conexão) em
    ModelUnavailable, para que o orchestrator escale para o próximo modelo da
    cadeia. Outros erros (ex.: 401 de chave inválida) propagam sem conversão,
    já que trocar de modelo gratuito não resolveria."""
    try:
        return client.chat.completions.create(model=model, messages=messages, tools=tools)
    except _INFRA_ERRORS as exc:
        raise ModelUnavailable(str(exc)) from exc
