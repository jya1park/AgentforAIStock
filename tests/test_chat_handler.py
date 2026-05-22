import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from src import chat_handler


def _reply(content: str = "", tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


def _tool_call(id: str, name: str, arguments: dict):
    return SimpleNamespace(
        id=id, type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def test_latest_report_returns_empty_when_no_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path / "nope")
    assert chat_handler._latest_report() == ""


def test_latest_report_skips_redteam_files(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    (tmp_path / "2026-05-20_morning.md").write_text("older body", encoding="utf-8")
    (tmp_path / "2026-05-21_morning.md").write_text("newest body", encoding="utf-8")
    (tmp_path / "2026-05-21_morning_redteam.md").write_text("redteam noise", encoding="utf-8")
    assert chat_handler._latest_report() == "newest body"


def test_build_context_includes_report_and_thesis(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    (tmp_path / "2026-05-21_morning.md").write_text("report body XYZ", encoding="utf-8")
    ctx = chat_handler._build_context()
    assert "report body XYZ" in ctx
    assert "도메인 thesis" in ctx


def test_answer_returns_text_when_no_tool_call(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    captured = {}
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _reply(content="단순 답변")
    def fake_create(model, messages, tools):
        captured["model"] = model
        captured["messages"] = messages
        captured["tools_count"] = len(tools)
        return _reply(content="단순 답변")
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)
    result = chat_handler.answer("오늘 시장 어때?")
    assert result == "단순 답변"
    assert captured["model"] == "gpt-4o"
    assert captured["tools_count"] == 4  # ticker_info, financials, fear_greed, market_breadth
    assert captured["messages"][-1] == {"role": "user", "content": "오늘 시장 어때?"}


def test_answer_executes_tool_call_and_returns_final_text(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(chat_handler, "fetch_ticker_info",
                        lambda ticker: {"ticker": ticker, "trailingPE": 28.5, "regularMarketPrice": 100.0})
    monkeypatch.setitem(chat_handler._TOOL_HANDLERS, "get_ticker_info",
                        lambda ticker: {"ticker": ticker, "trailingPE": 28.5, "regularMarketPrice": 100.0})

    call_count = {"n": 0}
    def fake_create(model, messages, tools):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _reply(tool_calls=[_tool_call("call_1", "get_ticker_info", {"ticker": "NVDA"})])
        # second call: model has tool result, returns final answer
        # verify tool result message present
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "trailingPE" in tool_msgs[0]["content"]
        return _reply(content="NVDA PER은 28.5배")

    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)
    result = chat_handler.answer("NVDA PER 얼마야?")
    assert result == "NVDA PER은 28.5배"
    assert call_count["n"] == 2


def test_answer_includes_history_in_messages(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    captured = {}
    def fake_create(model, messages, tools):
        captured["messages"] = messages
        return _reply(content="ok")
    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)
    history = [
        {"role": "user", "content": "직전 질문"},
        {"role": "assistant", "content": "직전 답변"},
    ]
    chat_handler.answer("후속 질문", history=history)
    roles = [m["role"] for m in captured["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert captured["messages"][1]["content"] == "직전 질문"
    assert captured["messages"][-1]["content"] == "후속 질문"


def test_run_tool_handles_handler_exception(monkeypatch):
    def boom(ticker): raise ValueError("yfinance down")
    monkeypatch.setitem(chat_handler._TOOL_HANDLERS, "get_ticker_info", boom)
    result = chat_handler._run_tool("get_ticker_info", json.dumps({"ticker": "X"}))
    payload = json.loads(result)
    assert "error" in payload
    assert "yfinance down" in payload["error"]


def test_run_tool_handles_unknown_tool():
    result = chat_handler._run_tool("nonexistent", "{}")
    assert "unknown tool" in json.loads(result)["error"]


def test_answer_gives_up_after_max_rounds(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(chat_handler, "MAX_TOOL_ROUNDS", 2)
    monkeypatch.setitem(chat_handler._TOOL_HANDLERS, "get_ticker_info", lambda ticker: {"ok": True})

    def always_tool(model, messages, tools):
        return _reply(tool_calls=[_tool_call("c", "get_ticker_info", {"ticker": "X"})])

    fake_client = MagicMock()
    fake_client.chat.completions.create = always_tool
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)
    result = chat_handler.answer("loop forever")
    assert "도구 호출이 너무 많아" in result


def test_answer_uses_context_override_when_provided(monkeypatch, tmp_path):
    """eval injects a fixed sample report via context_override; _build_context not called."""
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)  # empty, so _build_context would yield "(아직 ...)"
    captured = {}
    def fake_create(model, messages, tools):
        captured["system"] = messages[0]["content"]
        return _reply(content="ok")
    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)

    chat_handler.answer("질문", context_override="# 합성 리포트\nMY_UNIQUE_MARKER")
    assert "MY_UNIQUE_MARKER" in captured["system"]
    assert "아직 생성된 리포트가 없습니다" not in captured["system"]  # _build_context bypassed


def test_answer_falls_back_to_build_context_when_no_override(monkeypatch, tmp_path):
    """production path: no context_override → _build_context loads from REPORTS_DIR."""
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    captured = {}
    def fake_create(model, messages, tools):
        captured["system"] = messages[0]["content"]
        return _reply(content="ok")
    fake_client = MagicMock()
    fake_client.chat.completions.create = fake_create
    monkeypatch.setattr(chat_handler, "OpenAI", lambda: fake_client)

    chat_handler.answer("질문")
    assert "아직 생성된 리포트가 없습니다" in captured["system"]
