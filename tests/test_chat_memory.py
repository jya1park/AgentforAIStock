from src import chat_memory


def test_load_returns_empty_for_unknown_chat(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    assert chat_memory.load("999") == []


def test_append_persists_user_and_assistant_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    chat_memory.append("999", "hi", "hello")
    history = chat_memory.load("999")
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_append_truncates_to_max_turns(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(chat_memory, "MAX_TURNS", 3)
    for i in range(5):
        chat_memory.append("999", f"q{i}", f"a{i}")
    history = chat_memory.load("999")
    assert len(history) == 6  # 3 turns * 2 messages
    assert history[0]["content"] == "q2"  # oldest kept
    assert history[-1]["content"] == "a4"


def test_separate_chat_ids_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    chat_memory.append("111", "a", "b")
    chat_memory.append("222", "c", "d")
    assert chat_memory.load("111")[0]["content"] == "a"
    assert chat_memory.load("222")[0]["content"] == "c"


def test_clear_removes_only_target_chat(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    chat_memory.append("111", "a", "b")
    chat_memory.append("222", "c", "d")
    chat_memory.clear("111")
    assert chat_memory.load("111") == []
    assert chat_memory.load("222") != []


def test_clear_safe_when_no_history(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "nope.json")
    chat_memory.clear("999")  # must not raise


def test_load_recovers_from_corrupt_file(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", path)
    assert chat_memory.load("999") == []
