"""LLM-as-judge for qualitative grading dimensions that rules can't easily capture."""

import json

from openai import OpenAI

_ANALYST_JUDGE_PROMPT = """You evaluate a Korean stock-analysis LLM's output against its input payload.

Score each dimension 1-5 (5 = perfect):
- cross_check_clarity: Does the 시장 분위기 총평 section integrate VIX, F&G, and yield curve into a clear verdict (정렬 vs 충돌)?
- evidence_grounding: Are all cited tickers, prices, headlines verifiable in the payload?
- tone_consistency: Calm/declarative, no buy/sell calls, no emotion words like 폭등/급락
- thesis_usage: Does it cite ontology thesis keywords (capex, 후행 확산, 자금 이동) rather than just path names?

Also list up to 3 specific issues you noticed.

Return JSON: {{"cross_check_clarity": N, "evidence_grounding": N, "tone_consistency": N, "thesis_usage": N, "issues": ["..."]}}

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

Return JSON: {{"answer_relevance": N, "grounding": N, "format": N, "refusal_appropriateness": N, "issues": ["..."]}}"""


def judge_stock_analyst(payload: str, output: str, model: str = "gpt-4o") -> dict:
    """LLM-judge the qualitative dimensions of a stock-analyst output."""
    resp = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _ANALYST_JUDGE_PROMPT.format(payload=payload[:6000], output=output[:4000])}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


def judge_chat_answer(question: str, context: str, answer: str, model: str = "gpt-4o") -> dict:
    """LLM-judge a chat-assistant answer."""
    resp = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _CHAT_JUDGE_PROMPT.format(
            question=question, context=context[:3000], answer=answer[:2000])}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)
