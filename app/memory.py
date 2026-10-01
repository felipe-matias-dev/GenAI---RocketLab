from collections import defaultdict, deque


class SessionMemory:
    """Histórico de conversa em memória, por session_id.

    Não persiste entre reinícios do servidor — tradeoff aceito e documentado
    no README em troca de simplicidade (sem banco/Redis extra para o projeto).
    """

    def __init__(self, max_turns: int):
        self._max_turns = max_turns
        self._sessions: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._max_turns)
        )

    def get_history(self, session_id: str) -> list[dict]:
        return list(self._sessions[session_id])

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        self._sessions[session_id].append({"role": role, "content": content})
