import pandas as pd

from src.ontology import EtfCatalog, Ontology


def _ma_signal(close: float, ma5: float, ma20: float) -> str:
    above5, above20 = close > ma5, close > ma20
    if above5 and above20:
        return "above"
    if not above5 and not above20:
        return "below"
    return "mixed"


def _derived(r) -> dict:
    vol_surge = float(r.volume) / float(r.vol_avg20) if r.vol_avg20 > 0 else 0.0
    return {
        "vol_surge": round(vol_surge, 2),
        "volatility": round(float(r.volatility20), 2),
        "ma_signal": _ma_signal(float(r.close), float(r.ma5), float(r.ma20)),
    }


def analyze(
    df: pd.DataFrame,
    ontology: Ontology,
    etfs: EtfCatalog,
    top_n: int = 10,
) -> dict:
    """Structured snapshot: top/bottom movers, segments, ETFs.
    Each row carries change_pct, close, vol_surge, volatility, ma_signal.
    """
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
            **_derived(r),
        }

    seg_changes: dict[str, list[float]] = {}
    seg_vols: dict[str, list[float]] = {}
    for ticker in df.index:
        for tag in ontology.tags(ticker):
            seg_changes.setdefault(tag.segment, []).append(float(df.loc[ticker, "change_pct"]))
            seg_vols.setdefault(tag.segment, []).append(float(df.loc[ticker, "volatility20"]))
    segments = [
        {
            "segment": s,
            "avg_change_pct": round(sum(seg_changes[s]) / len(seg_changes[s]), 2),
            "avg_volatility": round(sum(seg_vols[s]) / len(seg_vols[s]), 2),
            "n": len(seg_changes[s]),
        }
        for s in seg_changes
    ]
    segments.sort(key=lambda x: x["avg_change_pct"], reverse=True)

    etf_rows = []
    for e in etfs.entries():
        if e["ticker"] not in df.index:
            continue
        r = df.loc[e["ticker"]]
        etf_rows.append({
            "ticker": e["ticker"],
            "theme": e.get("theme", ""),
            "change_pct": round(float(r.change_pct), 2),
            "close": round(float(r.close), 2),
            **_derived(r),
        })
    etf_rows.sort(key=lambda x: x["change_pct"], reverse=True)

    return {
        "top": [row(t) for t in top.index],
        "bottom": [row(t) for t in bottom.index],
        "segments": segments,
        "etfs": etf_rows,
    }


def _line(r: dict, is_etf: bool = False) -> str:
    label = r.get("segment") or r.get("theme", "")
    prefix = "[ETF] " if is_etf else ""
    return (
        f"- {prefix}{r['ticker']} ({label}): {r['change_pct']:+.2f}% | "
        f"vol {r['vol_surge']:.1f}x | vol20 {r['volatility']:.2f}% | "
        f"MA {r['ma_signal']} | close {r['close']}"
    )


def to_markdown(analysis: dict) -> str:
    """Serialize analysis dict to markdown for LLM input."""
    lines = ["# Daily Market Snapshot", "", "## Top Movers (stocks)"]
    lines += [_line(r) for r in analysis["top"]]
    lines += ["", "## Bottom Movers (stocks)"]
    lines += [_line(r) for r in analysis["bottom"]]
    lines += ["", "## Segment Rollup (simple average)"]
    for s in analysis["segments"]:
        lines.append(
            f"- {s['segment']}: {s['avg_change_pct']:+.2f}% | "
            f"vol20 {s['avg_volatility']:.2f}% | n={s['n']}"
        )
    lines += ["", "## ETF Summary (these are ETFs, not individual stocks)"]
    lines += [_line(r, is_etf=True) for r in analysis["etfs"]]
    return "\n".join(lines)
