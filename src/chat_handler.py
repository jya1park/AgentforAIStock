"""Multi-turn QA grounded in latest report + ontology thesis, with yfinance tool calls."""

import json

from openai import OpenAI

from src.agents import load_agent_prompt
from src.data_fetcher import fetch_financials, fetch_ticker_info
from src.macro import fetch_fear_greed
from src.main import REPORTS_DIR, _thesis_block
from src.ontology import Ontology

MODEL = "gpt-4o"
MAX_TOOL_ROUNDS = 3

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_ticker_info",
            "description": (
                "Current price, PER (P/E ratio), EPS, market cap, volume, 52-week high/low, "
                "sector for any stock ticker via yfinance. "
                "Works for US (NVDA, TSLA), Korean (005930.KS, 042700.KQ), ETFs (SOXX), crypto (BTC-USD). "
                "Call when the user asks about price, valuation, volume, or fundamentals of a specific ticker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Ticker symbol. US: NVDA. Korean: 005930.KS / 042700.KQ. ETF: SOXX. Crypto: BTC-USD.",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_financials",
            "description": (
                "Recent income statement for a stock ticker via yfinance — revenue, gross profit, "
                "operating income, net income, EBITDA. quarterly=True returns last ~4 quarters (default), "
                "False returns annual. "
                "Call when the user asks about earnings, sales/revenue trend, profit margins, "
                "QoQ/YoY growth, or specific quarter results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol (NVDA, 005930.KS, etc)."},
                    "quarterly": {
                        "type": "boolean",
                        "description": "True (default) for last ~4 quarters; False for annual statements.",
                    },
                },
                "required": ["ticker"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fear_greed",
            "description": (
                "CNN Fear & Greed Index — current US equity market sentiment as a 0-100 score "
                "(0 = extreme fear, 100 = extreme greed) plus rating and trend snapshot "
                "(previous_close, 1-week ago, 1-month ago, 1-year ago). "
                "Call when the user asks about market sentiment, fear & greed, investor mood, "
                "market psychology, or whether the market is overheated/fearful."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_TOOL_HANDLERS = {
    "get_ticker_info": fetch_ticker_info,
    "get_financials": fetch_financials,
    "get_fear_greed": fetch_fear_greed,
}


def _latest_report() -> str:
    if not REPORTS_DIR.exists():
        return ""
    reports = [p for p in REPORTS_DIR.glob("*.md") if "_redteam" not in p.name]
    if not reports:
        return ""
    return sorted(reports)[-1].read_text(encoding="utf-8")


def _build_context() -> str:
    report = _latest_report() or "(아직 생성된 리포트가 없습니다)"
    thesis = _thesis_block(Ontology.load().thesis_entries())
    return f"# 최근 리포트\n{report}\n\n{thesis}"


def _run_tool(name: str, arguments_json: str) -> str:
    handler = _TOOL_HANDLERS.get(name)
    if not handler:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        args = json.loads(arguments_json)
        return json.dumps(handler(**args), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


def answer(question: str, history: list[dict] | None = None) -> str:
    """Reply to question grounded in latest report + thesis, with multi-turn history and yfinance tools."""
    system = load_agent_prompt("chat-assistant") + "\n\n" + _build_context()
    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    client = OpenAI()
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": _run_tool(tc.function.name, tc.function.arguments),
            })
    return "도구 호출이 너무 많아 답변을 완성하지 못했습니다. 질문을 다시 정리해 주세요."
