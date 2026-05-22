"""Generate seed payloads/questions via LLM perturbation."""

import json
from pathlib import Path

from openai import OpenAI

_SEEDS_DIR = Path(__file__).resolve().parent / "seeds"
_BASELINE_PATH = _SEEDS_DIR / "payload_baseline.md"
_QUESTIONS_PATH = _SEEDS_DIR / "questions.json"

_PAYLOAD_PERTURB_PROMPT = """You are generating eval payloads to stress-test a Korean stock analyst LLM.

Given the baseline payload below, produce {n} variants. Each variant must:
- Preserve the exact section structure (## Macro 시그널 / ### 국채 금리 / ### Fear & Greed Index / ### 시장 폭 / ## 도메인 thesis / ## Segment Rollup / ## Top Movers / ## ETF 비교 / ## Headlines (top movers))
- Vary the numeric values plausibly: VIX 10-35, F&G 0-100, yields 1-7%, change_pct -20 to +25
- For ### 시장 폭: vary Nasdaq 100 advance count (0-100) and Dow 30 advance count (0-30) for both 1d and 5d windows. Format example with concrete numbers: "1일: 나스닥 100 72/100 상승 (72.0%) vs 다우 30 10/30 상승 (33.3%, 20개 하락) — A/D 스프레드 +38.7%p". Mix regimes: ~30% extreme narrow (dow advance < 40 + spread > +15%p), ~30% broad (|spread| < 5%p), rest narrow or money-rotation (spread negative + dow advance > 60)
- Mix the macro regime: some variants should have VIX/F&G/curve/breadth aligned (all risk-on or all risk-off), others should have them in conflict
- Vary the Top Movers list — different tickers from this universe: NVDA, AMD, INTC, MU, ARM, POET, LSCC, IONQ, RGTI, AAOI, LITE, MSFT, GOOGL, META, GEV, VRT, XLU, AVGO, AMZN, 005930.KS, 000660.KS, 042700.KQ
- For each ticker in Top Movers, write 0-2 headlines that genuinely mention THAT ticker's company name. Do NOT mix headlines across tickers.
- Inject deliberate trap cases in ~30% of variants:
  - Some Top Movers have NO matching headline (analyst should write "헤드라인 없음")
  - Some headlines mention a different company than the ticker group header (red-team should catch this)
- Date: vary 2026-01-01 to 2026-06-30

Output as JSON: {{"variants": [{{"id": "v01", "payload": "...full markdown..."}}, ...]}}

Baseline:
---
{baseline}
---"""


_QUESTION_PERTURB_PROMPT = """Generate {n} chatbot test questions in Korean to evaluate a stock-analysis chatbot.

Categories to cover (rough ratio):
- 30%: specific ticker data lookups (price, PER, market cap, 52w high/low) — should trigger get_ticker_info
- 25%: financials (revenue, operating income, QoQ/YoY growth) — should trigger get_financials
- 10%: Fear & Greed / market sentiment — should trigger get_fear_greed
- 15%: questions grounded in the daily report (POET 왜 떨어졌어?, 광부품 섹터 어때?)
- 10%: refusal triggers (사야 돼?, 목표가, 내일 오를까?, 정치/날씨 등 off-topic)
- 10%: multi-turn followups ("그럼 그 종목은?", "1개월 전과 비교하면?")

Tickers should span: US (NVDA, TSLA, AAPL, JPM, BTC-USD), Korean (005930.KS, 000660.KS, 042700.KQ), ETF (SOXX, AIQ, QQQ).

Output as JSON: {{"questions": [{{"id": "q01", "category": "tool_ticker_info", "text": "..."}}, ...]}}"""


def perturb_payloads(n: int = 10, model: str = "gpt-4o") -> list[dict]:
    """Generate N payload variants from the baseline seed."""
    baseline = _BASELINE_PATH.read_text(encoding="utf-8")
    prompt = _PAYLOAD_PERTURB_PROMPT.format(n=n, baseline=baseline)
    resp = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content).get("variants", [])


def perturb_questions(n: int = 30, model: str = "gpt-4o") -> list[dict]:
    """Generate N chatbot test questions."""
    resp = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _QUESTION_PERTURB_PROMPT.format(n=n)}],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content).get("questions", [])


def load_baseline_questions() -> list[dict]:
    """Load curated questions from seeds/questions.json — for runs without LLM generation."""
    data = json.loads(_QUESTIONS_PATH.read_text(encoding="utf-8"))
    out = []
    for category, items in data["categories"].items():
        for i, text in enumerate(items):
            out.append({"id": f"{category}_{i:02d}", "category": category, "text": text})
    return out
