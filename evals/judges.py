"""LLM-as-judge using Claude (separates eval model from production gpt-4o)."""

import json
import re

from anthropic import Anthropic

DEFAULT_JUDGE_MODEL = "claude-sonnet-4-6"

_ANALYST_JUDGE_PROMPT = """You evaluate a Korean stock-analysis LLM's output against its input payload.

Score each dimension 1-5 (5 = perfect):
- cross_check_clarity: Does the 시장 분위기 총평 section integrate VIX, F&G, and yield curve into a clear verdict (정렬 vs 충돌)?
- evidence_grounding: Are all cited tickers, prices, headlines verifiable in the payload?
- tone_consistency: Calm/declarative, no buy/sell calls, no emotion words like 폭등/급락
- thesis_usage: Does it cite ontology thesis keywords (capex, 후행 확산, 자금 이동) rather than just path names?

Also list up to 3 specific issues you noticed.

Return JSON only (no markdown, no prose): {{"cross_check_clarity": N, "evidence_grounding": N, "tone_consistency": N, "thesis_usage": N, "issues": ["..."]}}

PAYLOAD:
---
{payload}
---

OUTPUT:
---
{output}
---"""


_CHAT_JUDGE_PROMPT = """You evaluate a Korean stock-analysis chatbot's answer.

Question: {question}
Context (recent report excerpt): {context}
Answer: {answer}

Score 1-5:
- answer_relevance: Does the answer address the question?
- grounding: Is the answer based on the context/tool results, not training-data guesses?
- format: 2-5 sentences, plain text (no markdown headers), Korean ticker format
- refusal_appropriateness: If the question asks for buy/sell calls or off-topic, does it refuse correctly?

List up to 3 issues.

Return JSON only (no markdown, no prose): {{"answer_relevance": N, "grounding": N, "format": N, "refusal_appropriateness": N, "issues": ["..."]}}"""


def _extract_json(text: str) -> dict:
    """Claude sometimes wraps JSON in ```json fences; strip if present."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in response: {text[:200]}")
    return json.loads(m.group(0))


def _call_claude(prompt: str, model: str, max_tokens: int = 1024) -> dict:
    resp = Anthropic().messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(resp.content[0].text)


def judge_stock_analyst(payload: str, output: str, model: str = DEFAULT_JUDGE_MODEL) -> dict:
    """Claude-judge the qualitative dimensions of a stock-analyst output."""
    return _call_claude(_ANALYST_JUDGE_PROMPT.format(payload=payload[:6000], output=output[:4000]), model)


def judge_chat_answer(question: str, context: str, answer: str, model: str = DEFAULT_JUDGE_MODEL) -> dict:
    """Claude-judge a chat-assistant answer."""
    return _call_claude(
        _CHAT_JUDGE_PROMPT.format(question=question, context=context[:3000], answer=answer[:2000]),
        model,
    )
