from src import chat_handler


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
    assert "# 최근 리포트" in ctx
    assert "report body XYZ" in ctx
    assert "도메인 thesis" in ctx  # _thesis_block emits this header


def test_build_context_handles_missing_report(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    ctx = chat_handler._build_context()
    assert "아직 생성된 리포트가 없습니다" in ctx


def test_answer_calls_chat_assistant_with_context(monkeypatch, tmp_path):
    monkeypatch.setattr(chat_handler, "REPORTS_DIR", tmp_path)
    (tmp_path / "2026-05-21_morning.md").write_text("today fake body", encoding="utf-8")
    captured = {}
    def fake_call(name, user_input, model="gpt-4o-mini"):
        captured["name"] = name
        captured["input"] = user_input
        captured["model"] = model
        return "fake answer"
    monkeypatch.setattr(chat_handler, "call_agent", fake_call)
    result = chat_handler.answer("오늘 NVDA 어때?")
    assert result == "fake answer"
    assert captured["name"] == "chat-assistant"
    assert captured["model"] == "gpt-4o"
    assert "today fake body" in captured["input"]
    assert "# 질문\n오늘 NVDA 어때?" in captured["input"]
