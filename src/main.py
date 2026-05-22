"""Daily AI-stock report. mode=morning (US-close) or evening (KR-close)."""

import argparse
import re
from datetime import date, datetime, timezone
from pathlib import Path

from src.agents import call_agent
from src.analyzer import analyze, to_markdown
from src.data_fetcher import fetch_quotes
from src.macro import (
    breadth_block,
    fear_greed_block,
    fetch_breadth,
    fetch_fear_greed,
    fetch_vix,
    fetch_yields,
    macro_block,
    yields_block,
)
from src.news_fetcher import fetch_headlines
from src.ontology import EtfCatalog, Ontology
from src.telegram_notifier import send_message

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _is_kr(ticker: str) -> bool:
    return ticker.endswith(".KS") or ticker.endswith(".KQ")


def _filter_by_mode(tickers: list[str], mode: str) -> list[str]:
    if mode == "morning":
        return [t for t in tickers if not _is_kr(t)]
    if mode == "evening":
        return [t for t in tickers if _is_kr(t)]
    raise ValueError(f"unknown mode: {mode}")


def _extract_long_body(raw: str) -> str:
    """Extract body inside ```long_markdown ... ``` fence. Fallback: whole text.
    Strip auto-generated trailing disclaimer sections (## 면책 / ## Disclaimer / etc) —
    LLM sometimes adds them despite the prompt rule, so we cut anything after 시나리오."""
    m = re.search(r"```long_markdown\s*\n(.*?)```", raw, re.DOTALL)
    body = m.group(1).strip() if m else raw.strip()
    body = re.sub(
        r"\n##\s+(면책|Disclaimer|Risk Warning|주의사항|Caution)\b.*\Z",
        "", body, flags=re.DOTALL | re.IGNORECASE,
    )
    return body.strip()


def _age_label(now: datetime, dt: datetime) -> str:
    hours = (now - dt).total_seconds() / 3600
    if hours < 1:
        return "<1h ago"
    if hours < 48:
        return f"{int(hours)}h ago"
    return f"{int(hours / 24)}d ago"


def _news_section(headlines: dict[str, list[dict]], now: datetime | None = None, max_age_hours: int = 72) -> str:
    """Headlines sorted newest first, age stamped, items older than cutoff or
    without parseable timestamp dropped (no freshness ⇒ noise)."""
    now = now or datetime.now(timezone.utc)
    lines = ["", "## Headlines (top movers, ≤72h)"]
    for ticker, items in headlines.items():
        fresh = [
            it for it in items
            if it.get("published_at") and (now - it["published_at"]).total_seconds() / 3600 <= max_age_hours
        ]
        if not fresh:
            continue
        fresh.sort(key=lambda x: x["published_at"], reverse=True)
        lines.append(f"### {ticker}")
        for it in fresh:
            lines.append(f"- ({it['publisher']}, {_age_label(now, it['published_at'])}) {it['title']}")
    return "\n".join(lines)


def _thesis_block(theses: list[dict]) -> str:
    if not theses:
        return ""
    lines = ["## 도메인 thesis (ontology — 거품·강세 판단 참고)"]
    for t in theses:
        lines.append(f"- **{t['path']}**: {t['thesis']}")
    return "\n".join(lines) + "\n"


def main(mode: str, top_n: int = 10, per_ticker_news: int = 3) -> Path | None:
    ontology = Ontology.load()
    etfs = EtfCatalog.load()
    tickers = _filter_by_mode(list(ontology.all_tickers) + etfs.all_tickers(), mode)
    print(f"[{mode}] fetching {len(tickers)} tickers...")
    df = fetch_quotes(tickers)
    if df.empty:
        print("no quotes returned; abort")
        return None

    analysis = analyze(df, ontology, etfs, top_n=top_n)
    mover_tickers = [r["ticker"] for r in analysis["top"] + analysis["bottom"]]
    stock_movers = [t for t in mover_tickers if t in ontology.all_tickers]
    print(f"fetching news for {len(stock_movers)} movers...")
    headlines = fetch_headlines(stock_movers, ontology, per_ticker=per_ticker_news)

    today_iso = date.today().isoformat()
    vix_data = fetch_vix()
    yields_data = fetch_yields()
    fg_data = fetch_fear_greed()
    breadth_data = fetch_breadth()
    payload = (
        f"# 시점\n오늘: {today_iso} (이 날짜를 현재로 간주, 학습 cutoff 무시)\n\n"
        + macro_block(vix_data)
        + yields_block(yields_data)
        + fear_greed_block(fg_data)
        + breadth_block(breadth_data)
        + "\n"
        + _thesis_block(ontology.thesis_entries())
        + "\n"
        + to_markdown(analysis)
        + "\n"
        + _news_section(headlines)
    )
    print("calling stock-analyst agent (gpt-4o)...")
    raw = call_agent("stock-analyst", f"mode={mode}\n\n{payload}", model="gpt-5.4")
    long_body = _extract_long_body(raw)

    print("calling red-team agent (gpt-4o) for fact-check...")
    review = call_agent(
        "red-team",
        f"# 입력 페이로드\n{payload}\n\n# 분석가 리포트\n{long_body}",
        model="gpt-5.4",
    )

    REPORTS_DIR.mkdir(exist_ok=True)
    stem = f"{date.today().isoformat()}_{mode}"
    out_md = REPORTS_DIR / f"{stem}.md"
    out_review = REPORTS_DIR / f"{stem}_redteam.md"
    out_md.write_text(long_body, encoding="utf-8")
    out_review.write_text(review, encoding="utf-8")
    print(f"saved {out_md} ({len(long_body)} chars)")
    print(f"saved {out_review}")

    if long_body:
        sent = send_message(long_body)
        print(f"telegram: {'sent' if sent else 'skipped (no creds or network error)'}")

    return out_md


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["morning", "evening"])
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--per-ticker-news", type=int, default=3)
    args = p.parse_args()
    main(args.mode, args.top_n, args.per_ticker_news)
