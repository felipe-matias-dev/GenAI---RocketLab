import json

import numpy as np

from app.config import EMBEDDINGS_IDS_PATH, EMBEDDINGS_PATH

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SYNOPSIS_MAX_CHARS = 500

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _encode(texts: list[str]) -> np.ndarray:
    return _get_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def _fetch_synopses_from_db() -> list[dict]:
    from app.db import run_query

    rows = run_query(
        "SELECT sk_movie_id, titulo, sinopse FROM dim_movies "
        "WHERE sinopse IS NOT NULL AND TRIM(sinopse) != ''"
    )
    return rows


def build_index(db_rows: list[dict] | None = None) -> None:
    """Gera embeddings locais para as sinopses e persiste em disco.

    Não usa a API do OpenRouter — roda inteiramente local via
    sentence-transformers, então não consome a cota diária de requisições.
    """
    rows = db_rows if db_rows is not None else _fetch_synopses_from_db()

    texts = [row["sinopse"][:SYNOPSIS_MAX_CHARS] for row in rows]
    vectors = _encode(texts) if texts else np.zeros((0, 0), dtype="float32")

    metadata = [
        {
            "sk_movie_id": row["sk_movie_id"],
            "titulo": row["titulo"],
            "sinopse": row["sinopse"][:SYNOPSIS_MAX_CHARS],
        }
        for row in rows
    ]

    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(EMBEDDINGS_PATH, vectors)
    EMBEDDINGS_IDS_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )


def _load_index() -> tuple[np.ndarray, list[dict]]:
    if not EMBEDDINGS_PATH.exists() or not EMBEDDINGS_IDS_PATH.exists():
        print("Índice de embeddings não encontrado — gerando pela primeira vez...")
        build_index()

    vectors = np.load(EMBEDDINGS_PATH)
    metadata = json.loads(EMBEDDINGS_IDS_PATH.read_text(encoding="utf-8"))
    return vectors, metadata


def semantic_search(query: str, k: int = 5) -> list[dict]:
    vectors, metadata = _load_index()
    if len(metadata) == 0:
        return []

    query_vector = _encode([query])[0]
    similarities = vectors @ query_vector
    top_indices = np.argsort(-similarities)[:k]

    return [
        {**metadata[i], "score": float(similarities[i])} for i in top_indices
    ]
