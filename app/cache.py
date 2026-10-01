import json
import re
from pathlib import Path
from typing import Any, Optional

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    """Normaliza uma pergunta para uso como chave de cache.

    Minúsculas, espaços colapsados e sem espaços nas pontas — perguntas
    que só diferem em caixa ou espaçamento reaproveitam a mesma resposta.
    """
    return _WHITESPACE_RE.sub(" ", question.strip().lower())


class ResponseCache:
    """Cache de pergunta normalizada -> resposta, persistido em JSON.

    Só é usado para perguntas sem histórico de sessão (ver orchestrator.py):
    o objetivo é evitar gastar a cota diária do OpenRouter repetindo
    perguntas já respondidas antes.
    """

    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, question: str) -> Optional[Any]:
        return self._data.get(normalize_question(question))

    def set(self, question: str, value: Any) -> None:
        self._data[normalize_question(question)] = value
        self._save()
