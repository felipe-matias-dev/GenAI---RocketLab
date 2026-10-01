import json

import numpy as np
import pytest

from app import embeddings


FAKE_VECTORS = {
    "Nave espacial explora galáxia distante": np.array([1.0, 0.0], dtype="float32"),
    "Detetive resolve crime em cidade grande": np.array([0.0, 1.0], dtype="float32"),
}


def fake_encode(texts):
    return np.array([FAKE_VECTORS[t] for t in texts], dtype="float32")


@pytest.fixture
def isolated_index(tmp_path, monkeypatch):
    monkeypatch.setattr(embeddings, "EMBEDDINGS_PATH", tmp_path / "embeddings.npy")
    monkeypatch.setattr(embeddings, "EMBEDDINGS_IDS_PATH", tmp_path / "ids.json")
    monkeypatch.setattr(embeddings, "_encode", fake_encode)
    return tmp_path


ROWS = [
    {"sk_movie_id": "m1", "titulo": "Filme Espacial", "sinopse": "Nave espacial explora galáxia distante"},
    {"sk_movie_id": "m2", "titulo": "Filme Policial", "sinopse": "Detetive resolve crime em cidade grande"},
]


def test_build_index_persists_vectors_and_metadata(isolated_index):
    embeddings.build_index(db_rows=ROWS)

    assert embeddings.EMBEDDINGS_PATH.exists()
    assert embeddings.EMBEDDINGS_IDS_PATH.exists()

    meta = json.loads(embeddings.EMBEDDINGS_IDS_PATH.read_text(encoding="utf-8"))
    assert [row["titulo"] for row in meta] == ["Filme Espacial", "Filme Policial"]


def test_semantic_search_returns_most_similar_first(isolated_index, monkeypatch):
    embeddings.build_index(db_rows=ROWS)
    monkeypatch.setattr(
        embeddings, "_encode", lambda texts: np.array([[0.0, 1.0]], dtype="float32")
    )

    results = embeddings.semantic_search("crime na cidade", k=1)

    assert results[0]["titulo"] == "Filme Policial"


def test_semantic_search_builds_lazily_when_index_missing(isolated_index, monkeypatch):
    assert not embeddings.EMBEDDINGS_PATH.exists()
    monkeypatch.setattr(embeddings, "_fetch_synopses_from_db", lambda: ROWS)
    monkeypatch.setattr(
        embeddings, "_encode", lambda texts: np.array([FAKE_VECTORS[t] for t in texts], dtype="float32")
        if all(t in FAKE_VECTORS for t in texts)
        else np.array([[1.0, 0.0]], dtype="float32"),
    )

    results = embeddings.semantic_search("nave no espaço", k=1)

    assert embeddings.EMBEDDINGS_PATH.exists()
    assert results[0]["titulo"] == "Filme Espacial"
