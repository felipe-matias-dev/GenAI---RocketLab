from app.llm import get_client
from app.config import OPENROUTER_BASE_URL


def test_get_client_points_to_openrouter():
    client = get_client(api_key="test-key")
    assert str(client.base_url).rstrip("/") == OPENROUTER_BASE_URL.rstrip("/")
    assert client.api_key == "test-key"
