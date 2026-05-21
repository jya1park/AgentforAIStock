from datetime import date
from pathlib import Path

import pandas as pd

from unittest.mock import MagicMock

from src import data_fetcher
from src.data_fetcher import fetch_financials, fetch_quotes, fetch_ticker_info


def test_cache_hit_returns_pickled(tmp_path, monkeypatch):
    monkeypatch.setattr(data_fetcher, "CACHE_DIR", tmp_path)
    today = date(2026, 5, 19)
    expected = pd.DataFrame(
        [{"close": 100.0, "prev_close": 95.0, "change_pct": 5.26, "volume": 1e6,
          "ma5": 98.0, "ma20": 90.0, "vol_avg20": 8e5, "volatility20": 2.0}],
        index=pd.Index(["NVDA"], name="ticker"),
    )
    expected.to_pickle(tmp_path / f"yf_cache_{today.isoformat()}.pkl")

    df = fetch_quotes(["NVDA"], today=today)

    assert df.index.tolist() == ["NVDA"]
    assert df.loc["NVDA", "close"] == 100.0


def test_stale_schema_cache_is_ignored(tmp_path, monkeypatch):
    """Cache missing new columns should be refetched, not silently reused."""
    monkeypatch.setattr(data_fetcher, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data_fetcher.yf, "download", lambda **kw: pd.DataFrame())
    today = date(2026, 5, 19)
    pd.DataFrame(
        [{"close": 100.0, "prev_close": 95.0, "change_pct": 5.26, "volume": 1e6, "ma5": 98.0, "ma20": 90.0}],
        index=pd.Index(["NVDA"], name="ticker"),
    ).to_pickle(tmp_path / f"yf_cache_{today.isoformat()}.pkl")

    df = fetch_quotes(["NVDA"], today=today)
    assert df.empty  # refetch attempted, all failed → empty


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


def test_fetch_ticker_info_strips_none_fields(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "shortName": "Nvidia",
        "trailingPE": 32.5,
        "regularMarketPrice": 800.0,
        "regularMarketVolume": 5_000_000,
        "marketCap": 2_000_000_000_000,
        "sector": "Technology",
        "dividendYield": None,  # explicitly None — should be dropped
        "industry": None,
    }
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    result = fetch_ticker_info("NVDA")
    assert result["ticker"] == "NVDA"
    assert result["trailingPE"] == 32.5
    assert result["marketCap"] == 2_000_000_000_000
    assert "dividendYield" not in result
    assert "industry" not in result


def test_fetch_ticker_info_returns_empty_on_exception(monkeypatch):
    def boom(t): raise RuntimeError("yfinance down")
    monkeypatch.setattr(data_fetcher.yf, "Ticker", boom)
    assert fetch_ticker_info("NVDA") == {}


def test_fetch_ticker_info_returns_empty_when_info_empty(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.info = {}
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    assert fetch_ticker_info("BOGUS") == {}


def test_fetch_financials_returns_recent_quarters(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.quarterly_financials = pd.DataFrame(
        {
            pd.Timestamp("2026-01-31"): {"Total Revenue": 22.1e9, "Operating Income": 13.6e9, "Net Income": 12.3e9},
            pd.Timestamp("2025-10-31"): {"Total Revenue": 18.1e9, "Operating Income": 10.4e9, "Net Income": 9.2e9},
        }
    )
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    result = fetch_financials("NVDA")
    assert result["ticker"] == "NVDA"
    assert result["period_type"] == "quarterly"
    assert len(result["periods"]) == 2
    assert result["periods"][0]["end"] == "2026-01-31"
    assert result["periods"][0]["revenue"] == 22.1e9
    assert result["periods"][0]["net_income"] == 12.3e9


def test_fetch_financials_skips_nan_fields(monkeypatch):
    import numpy as np
    fake_ticker = MagicMock()
    fake_ticker.quarterly_financials = pd.DataFrame(
        {pd.Timestamp("2026-01-31"): {"Total Revenue": 1e9, "Operating Income": np.nan}}
    )
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    result = fetch_financials("X")
    assert result["periods"][0]["revenue"] == 1e9
    assert "operating_income" not in result["periods"][0]


def test_fetch_financials_returns_empty_when_yfinance_empty(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.quarterly_financials = pd.DataFrame()
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    assert fetch_financials("X") == {}


def test_fetch_financials_returns_empty_on_exception(monkeypatch):
    def boom(t): raise RuntimeError("yfinance down")
    monkeypatch.setattr(data_fetcher.yf, "Ticker", boom)
    assert fetch_financials("X") == {}


def test_fetch_financials_annual_uses_annual_frame(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.financials = pd.DataFrame(
        {pd.Timestamp("2025-12-31"): {"Total Revenue": 80e9, "Net Income": 30e9}}
    )
    fake_ticker.quarterly_financials = pd.DataFrame()  # quarterly empty, must not be used
    monkeypatch.setattr(data_fetcher.yf, "Ticker", lambda t: fake_ticker)
    result = fetch_financials("NVDA", quarterly=False)
    assert result["period_type"] == "annual"
    assert result["periods"][0]["revenue"] == 80e9
