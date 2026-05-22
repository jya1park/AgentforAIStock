"""Unit tests for Claude-based LLM judges (Anthropic SDK mocked)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from evals import judges


def _claude_text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(text=text)])


def test_judge_stock_analyst_calls_claude_with_payload_and_output(monkeypatch):
    fake_client = MagicMock()
    captured = {}
    def fake_create(model, max_tokens, messages):
        captured["model"] = model
        captured["messages"] = messages
        return _claude_text_response(
            '{"cross_check_clarity": 4, "evidence_grounding": 5, '
            '"tone_consistency": 5, "thesis_usage": 3, "issues": ["F&G trend not cited"]}'
        )
    fake_client.messages.create = fake_create
    monkeypatch.setattr(judges, "Anthropic", lambda: fake_client)

    result = judges.judge_stock_analyst("PAYLOAD body", "OUTPUT body")
    assert result["cross_check_clarity"] == 4
    assert result["thesis_usage"] == 3
    assert result["issues"] == ["F&G trend not cited"]
    assert captured["model"] == "claude-sonnet-4-6"
    assert "PAYLOAD body" in captured["messages"][0]["content"]
    assert "OUTPUT body" in captured["messages"][0]["content"]


def test_judge_chat_answer_parses_response(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create = lambda **kw: _claude_text_response(
        '{"answer_relevance": 5, "grounding": 4, "format": 5, '
        '"refusal_appropriateness": 5, "issues": []}'
    )
    monkeypatch.setattr(judges, "Anthropic", lambda: fake_client)

    result = judges.judge_chat_answer("NVDA PER?", "report context", "PER은 65배")
    assert result["answer_relevance"] == 5
    assert result["issues"] == []


def test_judge_chat_prompt_mentions_tool_environment(monkeypatch):
    """Judge must be told about the 4 live tools so tool-derived numbers aren't penalized."""
    captured = {}
    fake_client = MagicMock()
    def fake_create(model, max_tokens, messages):
        captured["prompt"] = messages[0]["content"]
        return _claude_text_response('{"answer_relevance": 5, "grounding": 5, "format": 5, "refusal_appropriateness": 5, "issues": []}')
    fake_client.messages.create = fake_create
    monkeypatch.setattr(judges, "Anthropic", lambda: fake_client)

    judges.judge_chat_answer("NVDA PER?", "report excerpt", "PER 65배")
    assert "get_ticker_info" in captured["prompt"]
    assert "get_financials" in captured["prompt"]
    assert "get_fear_greed" in captured["prompt"]
    assert "get_market_breadth" in captured["prompt"]
    assert "tool-result" in captured["prompt"].lower() or "tool result" in captured["prompt"].lower()


def test_extract_json_handles_fenced_response():
    """Claude sometimes wraps JSON in ```json``` even when told not to."""
    fenced = '```json\n{"answer_relevance": 4, "issues": []}\n```'
    result = judges._extract_json(fenced)
    assert result["answer_relevance"] == 4


def test_extract_json_handles_prose_wrapper():
    text = 'Here is my evaluation:\n{"answer_relevance": 3, "issues": ["too short"]}\nEnd.'
    result = judges._extract_json(text)
    assert result["answer_relevance"] == 3
    assert result["issues"] == ["too short"]


def test_judge_accepts_custom_model(monkeypatch):
    captured = {}
    fake_client = MagicMock()
    def fake_create(model, max_tokens, messages):
        captured["model"] = model
        return _claude_text_response('{"cross_check_clarity": 5, "evidence_grounding": 5, '
                                     '"tone_consistency": 5, "thesis_usage": 5, "issues": []}')
    fake_client.messages.create = fake_create
    monkeypatch.setattr(judges, "Anthropic", lambda: fake_client)

    judges.judge_stock_analyst("p", "o", model="claude-opus-4-7")
    assert captured["model"] == "claude-opus-4-7"
