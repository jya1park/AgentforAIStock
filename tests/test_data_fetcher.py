from datetime import date
from pathlib import Path

import pandas as pd

from src import data_fetcher
from src.data_fetcher import fetch_quotes


def test_cache_hit_returns_pickled(tmp_path, monkeypatch):
    monkeypatch.setattr(data_fetcher, "CACHE_DIR", tmp_path)
    today = date(2026, 5, 19)
    expected = pd.DataFrame(
        [{"close": 100.0, "prev_close": 95.0, "change_pct": 5.26, "volume": 1e6, "ma5": 98.0, "ma20": 90.0}],
        index=pd.Index(["NVDA"], name="ticker"),
    )
    expected.to_pickle(tmp_path / f"yf_cache_{today.isoformat()}.pkl")

    df = fetch_quotes(["NVDA"], today=today)

    assert df.index.tolist() == ["NVDA"]
    assert df.loc["NVDA", "close"] == 100.0


def test_all_fetches_fail_returns_empty_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(data_fetcher, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data_fetcher.yf, "download", lambda **kw: pd.DataFrame())
    df = fetch_quotes(["BOGUS"], today=date(2026, 5, 19))
    assert df.empty
    assert set(df.columns) == {"close", "prev_close", "change_pct", "volume", "ma5", "ma20", "vol_avg20", "volatility20"}


def test_columns_match_spec(tmp_path, monkeypatch):
    monkeypatch.setattr(data_fetcher, "CACHE_DIR", tmp_path)
    today = date(2026, 5, 19)
    pd.DataFrame(
        [{"close": 1.0, "prev_close": 1.0, "change_pct": 0.0, "volume": 0,
          "ma5": 1.0, "ma20": 1.0, "vol_avg20": 0, "volatility20": 1.5}],
        index=pd.Index(["X"], name="ticker"),
    ).to_pickle(tmp_path / f"yf_cache_{today.isoformat()}.pkl")

    df = fetch_quotes(["X"], today=today)

    assert set(df.columns) == {"close", "prev_close", "change_pct", "volume", "ma5", "ma20", "vol_avg20", "volatility20"}
