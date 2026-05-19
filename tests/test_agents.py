from unittest.mock import MagicMock

import pytest

from src import agents
from src.agents import call_agent, load_agent_prompt

AGENT_NAMES = [
    "stock-analyst", "red-team", "ai-systems-expert",
    "karpathy-reviewer", "ontology-curator", "news-curator", "kakao-writer",
]


@pytest.mark.parametrize("name", AGENT_NAMES)
def test_load_agent_prompt_strips_frontmatter(name):
    body = load_agent_prompt(name)
    assert not body.startswith("---")
    assert "name:" not in body.split("\n")[0]
    assert len(body) > 50


def test_call_agent_invokes_openai_with_system_and_user(monkeypatch):
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="mocked output"))]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_resp
    monkeypatch.setattr(agents, "OpenAI", lambda: fake_client)

    out = call_agent("stock-analyst", "test input")

    assert out == "mocked output"
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"
    assert kwargs["messages"][0]["role"] == "system"
    assert kwargs["messages"][1] == {"role": "user", "content": "test input"}
