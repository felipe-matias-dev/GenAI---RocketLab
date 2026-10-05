import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DB_PATH = BASE_DIR / os.environ.get("DB_PATH", "data/cinerocket.db")

CACHE_PATH = BASE_DIR / "data" / "cache.json"
EMBEDDINGS_PATH = BASE_DIR / "data" / "embeddings.npy"
EMBEDDINGS_IDS_PATH = BASE_DIR / "data" / "embeddings_ids.json"

MODEL_CHAIN = [
    "nvidia/nemotron-3.5-lightning:free",
    "z-ai/glm-5.2:free",
    "google/gemma-4-26b-a4b-it:free",
]

MAX_TOOL_ITERATIONS = 6
MAX_SESSION_TURNS = 6
DEFAULT_SQL_ROW_LIMIT = 500

# Prazo máximo de uma consulta SQL gerada pelo LLM. O banco tem ~745 mil linhas
# em bridge_movie_person; um JOIN mal ordenado passa de minutos sem esse corte.
SQL_TIMEOUT_SECONDS = 15

# Timeout por chamada ao OpenRouter. Sem isso, o SDK da OpenAI usa 600s de
# timeout padrão por chamada — um modelo ":free" congestionado prende a
# requisição por minutos antes de escalar para o próximo da cadeia. 20s é
# tempo suficiente para uma resposta normal, e curto o bastante para que o
# fallback (ModelUnavailable) entre em ação rápido quando o modelo travar.
LLM_REQUEST_TIMEOUT_SECONDS = 20
