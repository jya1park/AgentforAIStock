from src import chat_memory, telegram_bot


def test_handle_message_ignores_unknown_chat_id(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 123}, "text": "hi"})
    assert sent == []
    assert "ignored" in capsys.readouterr().out


def test_handle_message_replies_to_start(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append((text, chat_id)) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "/start"})
    assert len(sent) == 1
    assert "예시 질문" in sent[0][0]
    assert sent[0][1] == "999"


def test_handle_message_routes_text_to_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(telegram_bot, "answer", lambda q, history=None: f"reply to: {q}")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "POET 왜 떨어졌어?"})
    assert sent == ["reply to: POET 왜 떨어졌어?"]


def test_handle_message_persists_and_reuses_history(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    seen_histories = []
    def fake_answer(q, history=None):
        seen_histories.append(list(history or []))
        return f"answer-{len(seen_histories)}"
    monkeypatch.setattr(telegram_bot, "answer", fake_answer)
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: True)

    telegram_bot.handle_message({"chat": {"id": 999}, "text": "first"})
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "second"})

    assert seen_histories[0] == []  # first call: empty history
    assert seen_histories[1] == [   # second call: first turn now in history
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "answer-1"},
    ]


def test_handle_message_reset_clears_history(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    chat_memory.append("999", "old q", "old a")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "/reset"})
    assert sent == ["대화 기록을 초기화했습니다."]
    assert chat_memory.load("999") == []


def test_handle_message_sends_error_on_answer_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    def boom(q, history=None): raise RuntimeError("api down")
    monkeypatch.setattr(telegram_bot, "answer", boom)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "anything"})
    assert sent == ["일시적 오류로 답변 생성 실패. 잠시 후 다시 시도해 주세요."]
    assert chat_memory.load("999") == []  # failed turns not persisted


def test_handle_message_skips_empty_text(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(chat_memory, "MEMORY_PATH", tmp_path / "history.json")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    monkeypatch.setattr(telegram_bot, "answer", lambda q, history=None: "should not be called")
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "   "})
    telegram_bot.handle_message({"chat": {"id": 999}})  # no text key (photo, sticker, etc)
    assert sent == []
