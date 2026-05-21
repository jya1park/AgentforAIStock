from unittest.mock import MagicMock

import requests

from src.telegram_notifier import _split_for_telegram, send_message


def _ok_response() -> MagicMock:
    r = MagicMock()
    r.raise_for_status.return_value = None
    return r


def test_send_returns_false_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert send_message("hi", chat_id="123") is False


def test_send_returns_false_without_chat_id(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_message("hi", bot_token="abc") is False


def test_send_posts_to_bot_api(monkeypatch):
    captured = {}
    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _ok_response()
    monkeypatch.setattr(requests, "post", fake_post)
    assert send_message("hello", chat_id="123", bot_token="abc") is True
    assert captured["url"] == "https://api.telegram.org/botabc/sendMessage"
    assert captured["json"] == {"chat_id": "123", "text": "hello"}
    assert captured["timeout"] == 10


def test_send_returns_false_on_network_error(monkeypatch):
    def boom(*a, **kw): raise requests.ConnectionError()
    monkeypatch.setattr(requests, "post", boom)
    assert send_message("hi", chat_id="1", bot_token="t") is False


def test_send_returns_false_on_http_error(monkeypatch):
    fake = MagicMock()
    fake.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
    monkeypatch.setattr(requests, "post", lambda *a, **kw: fake)
    assert send_message("hi", chat_id="1", bot_token="bad_token") is False


def test_split_returns_single_chunk_when_under_limit():
    assert _split_for_telegram("short text", limit=4096) == ["short text"]


def test_split_prefers_blank_line_boundary():
    text = "para one line\n\npara two line\n\npara three line"
    chunks = _split_for_telegram(text, limit=20)
    assert all(len(c) <= 20 for c in chunks)
    assert chunks[0] == "para one line"
    assert "para two line" in chunks[1]


def test_split_falls_back_to_newline_when_no_blank_line():
    text = "line one\nline two\nline three\nline four"
    chunks = _split_for_telegram(text, limit=15)
    assert all(len(c) <= 15 for c in chunks)
    assert chunks[0] == "line one"


def test_split_hard_cuts_when_no_boundary():
    text = "x" * 50
    chunks = _split_for_telegram(text, limit=20)
    assert chunks == ["x" * 20, "x" * 20, "x" * 10]


def test_send_splits_long_message(monkeypatch):
    posts = []
    def fake_post(url, json, timeout):
        posts.append(json["text"])
        return _ok_response()
    monkeypatch.setattr(requests, "post", fake_post)
    long_text = ("a" * 4000) + "\n\n" + ("b" * 4000)
    assert send_message(long_text, chat_id="1", bot_token="t") is True
    assert len(posts) == 2
    assert all(len(p) <= 4096 for p in posts)


def test_send_uses_env_when_no_args(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "env_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "env_chat")
    captured = {}
    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _ok_response()
    monkeypatch.setattr(requests, "post", fake_post)
    assert send_message("via env") is True
    assert "env_token" in captured["url"]
    assert captured["json"]["chat_id"] == "env_chat"
