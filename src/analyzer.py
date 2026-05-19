import pandas as pd

from src.ontology import EtfCatalog, Ontology


def analyze(
    df: pd.DataFrame,
    ontology: Ontology,
    etfs: EtfCatalog,
    top_n: int = 10,
) -> dict:
    """Structured snapshot: top/bottom movers, per-segment average, ETF rollup."""
    ranked = df.dropna(subset=["change_pct"]).sort_values("change_pct")
    top = ranked.tail(top_n).iloc[::-1]
    bottom = ranked.head(top_n)

    def row(ticker: str) -> dict:
        r = df.loc[ticker]
        tags = ontology.tags(ticker)
        return {
            "ticker": ticker,
            "segment": tags[0].segment if tags else "etf",
            "change_pct": round(float(r.change_pct), 2),
            "close": round(float(r.close), 2),
        }

    seg_changes: dict[str, list[float]] = {}
    for ticker in df.index:
        for tag in ontology.tags(ticker):
            seg_changes.setdefault(tag.segment, []).append(float(df.loc[ticker, "change_pct"]))
    segments = [
        {"segment": s, "avg_change_pct": round(sum(v) / len(v), 2), "n": len(v)}
        for s, v in seg_changes.items()
    ]
    segments.sort(key=lambda x: x["avg_change_pct"], reverse=True)

    etf_rows = []
    for e in etfs.entries():
        if e["ticker"] not in df.index:
            continue
        etf_rows.append({
            "ticker": e["ticker"],
            "theme": e.get("theme", ""),
            "change_pct": round(float(df.loc[e["ticker"], "change_pct"]), 2),
        })
    etf_rows.sort(key=lambda x: x["change_pct"], reverse=True)

    return {
        "top": [row(t) for t in top.index],
        "bottom": [row(t) for t in bottom.index],
        "segments": segments,
        "etfs": etf_rows,
    }


def to_markdown(analysis: dict) -> str:
    """Serialize analysis dict to markdown for LLM input."""
    lines = ["# Daily Market Snapshot", "", "## Top Movers"]
    for r in analysis["top"]:
        lines.append(f"- {r['ticker']} ({r['segment']}): {r['change_pct']:+.2f}% — close {r['close']}")
    lines += ["", "## Bottom Movers"]
    for r in analysis["bottom"]:
        lines.append(f"- {r['ticker']} ({r['segment']}): {r['change_pct']:+.2f}% — close {r['close']}")
    lines += ["", "## Segment Rollup (simple average)"]
    for s in analysis["segments"]:
        lines.append(f"- {s['segment']}: {s['avg_change_pct']:+.2f}% (n={s['n']})")
    lines += ["", "## ETF Summary"]
    for e in analysis["etfs"]:
        lines.append(f"- {e['ticker']} ({e['theme']}): {e['change_pct']:+.2f}%")
    return "\n".join(lines)
