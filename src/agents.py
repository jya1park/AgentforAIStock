import re
from pathlib import Path

from openai import OpenAI

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"


def load_agent_prompt(name: str) -> str:
    """Read .claude/agents/{name}.md, strip YAML frontmatter, return body."""
    text = (AGENTS_DIR / f"{name}.md").read_text()
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    return text.strip()


def call_agent(name: str, user_input: str, model: str = "gpt-4o-mini") -> str:
    """Load agent system prompt and call OpenAI. Return response text."""
    resp = OpenAI().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": load_agent_prompt(name)},
            {"role": "user", "content": user_input},
        ],
    )
    return resp.choices[0].message.content
