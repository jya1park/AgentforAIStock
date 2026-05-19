import pandas as pd
import pytest

from src.analyzer import analyze, to_markdown
from src.ontology import EtfCatalog, Ontology


@pytest.fixture
def fake_df():
    return pd.DataFrame(
        [
            {"close": 100.0, "prev_close": 95.0, "change_pct": 5.0, "volume": 1e6, "ma5": 98.0, "ma20": 90.0},
            {"close": 200.0, "prev_close": 210.0, "change_pct": -4.8, "volume": 2e6, "ma5": 205.0, "ma20": 200.0},
            {"close": 50.0, "prev_close": 55.0, "change_pct": -9.1, "volume": 5e5, "ma5": 52.0, "ma20": 50.0},
            {"close": 80.0, "prev_close": 75.0, "change_pct": 6.7, "volume": 3e6, "ma5": 78.0, "ma20": 70.0},
        ],
        index=pd.Index(["NVDA", "MSFT", "AAOI", "PLTR"], name="ticker"),
    )


def test_top_and_bottom_sorted(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=2)
    assert [r["ticker"] for r in a["top"]] == ["PLTR", "NVDA"]
    assert [r["ticker"] for r in a["bottom"]] == ["AAOI", "MSFT"]


def test_segments_sorted_desc_and_aggregated(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load())
    pcts = [s["avg_change_pct"] for s in a["segments"]]
    assert pcts == sorted(pcts, reverse=True)
    assert all(s["n"] >= 1 for s in a["segments"])


def test_known_ticker_gets_segment_not_etf(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=4)
    nvda = next(r for r in a["top"] + a["bottom"] if r["ticker"] == "NVDA")
    assert nvda["segment"] != "etf"


def test_to_markdown_has_all_sections(fake_df):
    md = to_markdown(analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=2))
    for h in ["# Daily Market Snapshot", "## Top Movers", "## Bottom Movers",
              "## Segment Rollup", "## ETF Summary"]:
        assert h in md
    assert "PLTR" in md and "AAOI" in md
