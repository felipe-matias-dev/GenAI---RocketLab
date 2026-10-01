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
