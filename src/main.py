"""Daily AI-stock report. mode=morning (US-close) or evening (KR-close)."""

import argparse
from datetime import date
from pathlib import Path

from src.agents import call_agent
from src.analyzer import analyze, to_markdown
from src.data_fetcher import fetch_quotes
from src.news_fetcher import fetch_headlines
from src.ontology import EtfCatalog, Ontology

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"


def _is_kr(ticker: str) -> bool:
    return ticker.endswith(".KS") or ticker.endswith(".KQ")


def _filter_by_mode(tickers: list[str], mode: str) -> list[str]:
    if mode == "morning":
        return [t for t in tickers if not _is_kr(t)]
    if mode == "evening":
        return [t for t in tickers if _is_kr(t)]
    raise ValueError(f"unknown mode: {mode}")


def _news_section(headlines: dict[str, list[dict]]) -> str:
    lines = ["", "## Headlines (top movers)"]
    for ticker, items in headlines.items():
        if not items:
            continue
        lines.append(f"### {ticker}")
        for it in items:
            lines.append(f"- ({it['publisher']}) {it['title']}")
    return "\n".join(lines)


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

    payload = to_markdown(analysis) + "\n" + _news_section(headlines)
    print("calling stock-analyst agent...")
    report = call_agent("stock-analyst", f"mode={mode}\n\n{payload}")

    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"{date.today().isoformat()}_{mode}.md"
    out.write_text(report, encoding="utf-8")
    print(f"saved {out}")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["morning", "evening"])
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--per-ticker-news", type=int, default=3)
    args = p.parse_args()
    main(args.mode, args.top_n, args.per_ticker_news)
