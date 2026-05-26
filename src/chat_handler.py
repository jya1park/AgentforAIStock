"""Multi-turn QA grounded in latest report + ontology thesis, with yfinance tool calls."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from openai import OpenAI

from src.agents import load_agent_prompt
from src.chart import generate_price_chart, generate_segment_trend
from src.data_fetcher import fetch_financials, fetch_ticker_info
from src.macro import fetch_breadth, fetch_fear_greed
from src.main import REPORTS_DIR, _thesis_block
from src.ontology import Ontology

MODEL = "gpt-5.4"
MAX_TOOL_ROUNDS = 3


@dataclass
class ChatResult:
    text: str
    images: list[Path] = field(default_factory=list)

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
    {
        "type": "function",
        "function": {
            "name": "get_price_chart",
            "description": (
                "여러 종목/ETF의 가격 추이 비교 차트 생성. 정규화(시작일=100)해서 라인 비교. "
                "AI 관련 ETF: SOXX(반도체), AIQ(AI 광의), DTCR(데이터센터), QQQ(나스닥100), XLU(전력). "
                "사용자가 '펀드 주가 흐름', 'ETF 비교', 'NVDA vs AMD 차트', 'AI 펀드 추이' 등 물을 때 호출. "
                "여러 종목을 한 차트에 정규화해서 비교 가능."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "비교할 종목/ETF 티커 리스트. 예: ['SOXX', 'AIQ', 'QQQ'] 또는 ['NVDA', 'AMD', 'INTC']",
                    },
                    "days": {"type": "integer", "description": "최근 N일 (기본 30)"},
                },
                "required": ["tickers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_segment_trend",
            "description": (
                "세그먼트별 일별 등락률 트렌드 차트 생성 (양자컴퓨팅, 광모듈, GPU 가속기 등). "
                "최근 N일(기본 14) 라인 차트를 이미지로 생성합니다. "
                "사용자가 '세그먼트 트렌드', '섹터 추이 차트', '최근 2주 세그먼트', '트렌드 그래프' 등 물을 때 호출."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "최근 N일 (기본 14)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_breadth",
            "description": (
                "Tech sector (SOXX) vs broad market (SPY S&P 500) returns over 5 and 20 days, with spread (%p). "
                "Measures money concentration: narrow rally (market down + tech up, spread > 3%p) is a bubble "
                "entry signal; broad means money is spread across sectors. "
                "Call when the user asks about market breadth, narrow vs broad rally, money flow concentration, "
                "sector divergence, whether the rally is healthy, or comparisons like '기술주는 오르는데 나머지는 떨어진다'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

def _chart_price_comparison(tickers: list[str], days: int = 30) -> dict:
    path = generate_price_chart(tickers, days)
    if path:
        return {"chart_path": str(path), "summary": f"{', '.join(tickers)} 가격 비교 차트 ({days}일)를 생성했습니다."}
    return {"error": "가격 데이터를 가져올 수 없습니다. 티커를 확인해 주세요."}


def _chart_segment_trend(days: int = 14) -> dict:
    """Generate segment trend chart image. Returns {"chart_path": ..., "summary": ...} or {"error": ...}."""
    path = generate_segment_trend(days=days)
    if path:
        return {"chart_path": str(path), "summary": f"세그먼트 트렌드 차트 ({days}일)를 생성했습니다."}
    return {"error": "세그먼트 트렌드 데이터가 아직 충분하지 않습니다. morning 리포트를 며칠 더 실행해 주세요."}


_TOOL_HANDLERS = {
    "get_ticker_info": fetch_ticker_info,
    "get_financials": fetch_financials,
    "get_fear_greed": fetch_fear_greed,
    "get_market_breadth": fetch_breadth,
    "get_price_chart": _chart_price_comparison,
    "get_segment_trend": _chart_segment_trend,
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


def answer(question: str, history: list[dict] | None = None, context_override: str | None = None) -> ChatResult:
    """Reply to question grounded in latest report + thesis, with multi-turn history and yfinance tools.
    Returns ChatResult with text + optional image paths (for chart tools).
    context_override: if provided, use this string instead of loading the latest report — for eval reproducibility."""
    context = context_override if context_override is not None else _build_context()
    system = load_agent_prompt("chat-assistant") + "\n\n" + context
    messages = [{"role": "system", "content": system}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": question})

    images: list[Path] = []
    client = OpenAI()
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return ChatResult(text=msg.content or "", images=images)
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {"id": tc.id, "type": tc.type, "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            tool_result = _run_tool(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": tool_result})
            try:
                parsed = json.loads(tool_result)
                if isinstance(parsed, dict) and "chart_path" in parsed:
                    images.append(Path(parsed["chart_path"]))
            except (json.JSONDecodeError, TypeError):
                pass
    return ChatResult(text="도구 호출이 너무 많아 답변을 완성하지 못했습니다.", images=images)
