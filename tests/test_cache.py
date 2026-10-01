from app.cache import ResponseCache, normalize_question


def test_normalize_question_trims_and_lowercases():
    assert (
        normalize_question("  Quais Filmes   são os Mais POPULARES?  ")
        == "quais filmes são os mais populares?"
    )


def test_miss_returns_none(tmp_path):
    cache = ResponseCache(tmp_path / "cache.json")
    assert cache.get("pergunta que nunca foi feita") is None


def test_set_then_get_is_case_and_space_insensitive(tmp_path):
    cache = ResponseCache(tmp_path / "cache.json")
    cache.set("Top 10 filmes  com maior receita", {"answer": "resposta"})

    assert cache.get("top 10 filmes com maior receita") == {"answer": "resposta"}


def test_persists_to_disk_across_instances(tmp_path):
    path = tmp_path / "cache.json"
    cache = ResponseCache(path)
    cache.set("pergunta persistente", {"answer": "valor"})

    reloaded = ResponseCache(path)
    assert reloaded.get("pergunta persistente") == {"answer": "valor"}


def test_missing_file_does_not_raise(tmp_path):
    cache = ResponseCache(tmp_path / "does-not-exist-yet.json")
    assert cache.get("qualquer coisa") is None
