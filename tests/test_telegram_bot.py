from src import telegram_bot


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


def test_handle_message_routes_text_to_answer(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setattr(telegram_bot, "answer", lambda q: f"reply to: {q}")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "POET 왜 떨어졌어?"})
    assert sent == ["reply to: POET 왜 떨어졌어?"]


def test_handle_message_sends_error_on_answer_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    def boom(q): raise RuntimeError("api down")
    monkeypatch.setattr(telegram_bot, "answer", boom)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "anything"})
    assert sent == ["일시적 오류로 답변 생성 실패. 잠시 후 다시 시도해 주세요."]


def test_handle_message_skips_empty_text(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    sent = []
    monkeypatch.setattr(telegram_bot, "send_message", lambda text, chat_id=None: sent.append(text) or True)
    monkeypatch.setattr(telegram_bot, "answer", lambda q: "should not be called")
    telegram_bot.handle_message({"chat": {"id": 999}, "text": "   "})
    telegram_bot.handle_message({"chat": {"id": 999}})  # no text key (photo, sticker, etc)
    assert sent == []
