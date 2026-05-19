import pandas as pd
import pytest

from src.analyzer import analyze, to_markdown
from src.ontology import EtfCatalog, Ontology


@pytest.fixture
def fake_df():
    return pd.DataFrame(
        [
            {"close": 100.0, "prev_close": 95.0, "change_pct": 5.0, "volume": 3e6,
             "ma5": 98.0, "ma20": 90.0, "vol_avg20": 1e6, "volatility20": 2.5},
            {"close": 200.0, "prev_close": 210.0, "change_pct": -4.8, "volume": 2e6,
             "ma5": 205.0, "ma20": 220.0, "vol_avg20": 2e6, "volatility20": 1.8},
            {"close": 50.0, "prev_close": 55.0, "change_pct": -9.1, "volume": 5e5,
             "ma5": 52.0, "ma20": 60.0, "vol_avg20": 4e5, "volatility20": 4.2},
            {"close": 80.0, "prev_close": 75.0, "change_pct": 6.7, "volume": 3e6,
             "ma5": 78.0, "ma20": 70.0, "vol_avg20": 1.5e6, "volatility20": 3.1},
        ],
        index=pd.Index(["NVDA", "MSFT", "AAOI", "PLTR"], name="ticker"),
    )


def test_top_and_bottom_sorted(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=2)
    assert [r["ticker"] for r in a["top"]] == ["PLTR", "NVDA"]
    assert [r["ticker"] for r in a["bottom"]] == ["AAOI", "MSFT"]


def test_segments_have_avg_volatility(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load())
    for s in a["segments"]:
        assert "avg_volatility" in s and s["avg_volatility"] >= 0


def test_derived_fields_present(fake_df):
    a = analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=4)
    pltr = next(r for r in a["top"] if r["ticker"] == "PLTR")
    assert pltr["vol_surge"] == 2.0  # 3e6 / 1.5e6
    assert pltr["volatility"] == 3.1
    assert pltr["ma_signal"] == "above"  # close 80 > ma5 78 > ma20 70

    msft = next(r for r in a["bottom"] if r["ticker"] == "MSFT")
    assert msft["ma_signal"] == "below"  # close 200 < ma5 205, < ma20 220


def test_to_markdown_shows_signals(fake_df):
    md = to_markdown(analyze(fake_df, Ontology.load(), EtfCatalog.load(), top_n=2))
    for h in ["# Daily Market Snapshot", "## Top Movers", "## Bottom Movers",
              "## Segment Rollup", "## ETF Summary"]:
        assert h in md
    assert "vol " in md and "vol20 " in md and "MA above" in md
