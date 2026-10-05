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

# Conferir periodicamente em https://openrouter.ai/api/v1/models (filtrar por
# sufixo ":free" e "tools" em supported_parameters): modelos gratuitos somem.
MODEL_CHAIN = [
    "nvidia/nemotron-3.5-lightning:free",
    "qwen/qwen3.8-27b:free",
    "google/gemma-4-26b-a4b-it:free",
]

MAX_TOOL_ITERATIONS = 6
MAX_SESSION_TURNS = 6
DEFAULT_SQL_ROW_LIMIT = 500

# Prazo máximo de uma consulta SQL gerada pelo LLM. O banco tem ~745 mil linhas
# em bridge_movie_person; um JOIN mal ordenado passa de minutos sem esse corte. A consulta de
# dupla ator–diretor (a mais pesada) leva ~12s mesmo na forma otimizada, então
# 30s dá folga sem deixar o servidor preso indefinidamente.
SQL_TIMEOUT_SECONDS = 30

# Timeout por chamada ao OpenRouter. Sem isso, o SDK da OpenAI usa 600s de
# timeout padrão por chamada — um modelo ":free" congestionado prende a
# requisição por minutos antes de escalar para o próximo da cadeia. 20s é
# tempo suficiente para uma resposta normal, e curto o bastante para que o
# fallback (ModelUnavailable) entre em ação rápido quando o modelo travar.
LLM_REQUEST_TIMEOUT_SECONDS = 20

# O schema linking custa 1 chamada extra por pergunta (cota de 50/dia nos modelos
# :free). Desligável por SCHEMA_LINKING=off para medir se o ganho compensa — o
# schema completo continua indo no prompt de qualquer forma.
SCHEMA_LINKING_ENABLED = os.environ.get("SCHEMA_LINKING", "on").strip().lower() not in {"off", "0", "false", "no"}
