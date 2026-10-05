from app.llm import get_client
from app.config import OPENROUTER_BASE_URL


def test_get_client_points_to_openrouter():
    client = get_client(api_key="test-key")
    assert str(client.base_url).rstrip("/") == OPENROUTER_BASE_URL.rstrip("/")
    assert client.api_key == "test-key"


def test_get_groq_client_points_to_groq():
    from app.config import GROQ_BASE_URL
    from app.llm import get_groq_client

    client = get_groq_client(api_key="groq-key")
    assert str(client.base_url).rstrip("/") == GROQ_BASE_URL.rstrip("/")
    assert client.api_key == "groq-key"


def test_split_model_routes_prefixed_models_to_their_provider():
    from app.llm import split_model

    assert split_model("groq:openai/gpt-oss-120b") == ("groq", "openai/gpt-oss-120b")


def test_split_model_defaults_to_openrouter_for_free_model_ids():
    from app.llm import split_model

    # ":free" é sufixo do OpenRouter, não prefixo de provedor.
    assert split_model("qwen/qwen3.8-27b:free") == ("openrouter", "qwen/qwen3.8-27b:free")
