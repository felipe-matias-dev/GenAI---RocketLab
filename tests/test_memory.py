from app.memory import SessionMemory


def test_new_session_has_empty_history():
    memory = SessionMemory(max_turns=6)
    assert memory.get_history("session-1") == []


def test_add_turn_appends_to_history():
    memory = SessionMemory(max_turns=6)
    memory.add_turn("session-1", "user", "pergunta")
    memory.add_turn("session-1", "assistant", "resposta")

    assert memory.get_history("session-1") == [
        {"role": "user", "content": "pergunta"},
        {"role": "assistant", "content": "resposta"},
    ]


def test_history_capped_at_max_turns():
    memory = SessionMemory(max_turns=2)
    for i in range(5):
        memory.add_turn("session-1", "user", f"pergunta {i}")

    history = memory.get_history("session-1")
    assert len(history) == 2
    assert history[-1]["content"] == "pergunta 4"


def test_sessions_are_independent():
    memory = SessionMemory(max_turns=6)
    memory.add_turn("session-1", "user", "pergunta de A")
    memory.add_turn("session-2", "user", "pergunta de B")

    assert memory.get_history("session-1") == [{"role": "user", "content": "pergunta de A"}]
    assert memory.get_history("session-2") == [{"role": "user", "content": "pergunta de B"}]
