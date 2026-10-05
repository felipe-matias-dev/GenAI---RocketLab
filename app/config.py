import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_flag(name: str, default: str = "on") -> bool:
    return os.environ.get(name, default).strip().lower() not in {"off", "0", "false", "no"}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or default


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"

# Provedor reserva (opcional): o Groq expõe uma API compatível com a da OpenAI
# e o plano gratuito dá 1.000 requisições/dia ao openai/gpt-oss-120b (limite
# próprio, com 8K tokens/minuto), contra 50/dia somadas de todos os ":free" do
# OpenRouter. Só entra na cadeia se houver chave.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

DB_PATH = BASE_DIR / os.environ.get("DB_PATH", "data/cinerocket.db")

CACHE_PATH = BASE_DIR / "data" / "cache.json"
EMBEDDINGS_PATH = BASE_DIR / "data" / "embeddings.npy"
EMBEDDINGS_IDS_PATH = BASE_DIR / "data" / "embeddings_ids.json"

# Modelos ":free" somem ou perdem suporte a tools sem aviso. Por isso o app
# confere a cadeia contra o catálogo público do OpenRouter ao iniciar (ver
# app/model_catalog.py) e a ordem pode ser trocada sem mexer no código, pela
# variável OPENROUTER_MODELS (lista separada por vírgula).
OPENROUTER_MODELS = _env_list(
    "OPENROUTER_MODELS",
    [
        "nvidia/nemotron-3.5-lightning:free",
        # Substitui qwen/qwen3.8-27b:free, que saiu do catálogo em 05/10/2026
        # (detectado pela própria checagem de app/model_catalog.py).
        "nvidia/nemotron-3-super-120b-a12b:free",
        "google/gemma-4-26b-a4b-it:free",
    ],
)
GROQ_MODELS = _env_list("GROQ_MODELS", ["openai/gpt-oss-120b"])

# Modelos de outro provedor levam o prefixo "<provedor>:" (ver app/llm.py).
# O OpenRouter vem primeiro porque é o provedor sugerido pelo enunciado; o
# Groq é a última linha da cadeia, para quando a cota diária acabar.
MODEL_CHAIN = OPENROUTER_MODELS + (
    [f"groq:{model}" for model in GROQ_MODELS] if GROQ_API_KEY else []
)

# A checagem do catálogo é uma chamada pública ao OpenRouter que não consome
# cota; MODEL_CATALOG_CHECK=off a desliga (os testes desligam para não usar rede).
MODEL_CATALOG_CHECK_ENABLED = _env_flag("MODEL_CATALOG_CHECK")
MODEL_CATALOG_TIMEOUT_SECONDS = 5

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
SCHEMA_LINKING_ENABLED = _env_flag("SCHEMA_LINKING")
