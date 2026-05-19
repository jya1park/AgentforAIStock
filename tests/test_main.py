import pandas as pd
import pytest

from src import main
from src.main import _filter_by_mode, _is_kr, _news_section


def test_is_kr_suffixes():
    assert _is_kr("005930.KS") is True
    assert _is_kr("042700.KQ") is True
    assert _is_kr("NVDA") is False
    assert _is_kr("QQQ") is False


def test_filter_by_mode_morning_drops_kr():
    assert _filter_by_mode(["NVDA", "AAOI", "005930.KS", "069500.KS"], "morning") == ["NVDA", "AAOI"]


def test_filter_by_mode_evening_keeps_only_kr():
    assert _filter_by_mode(["NVDA", "005930.KS", "042700.KQ"], "evening") == ["005930.KS", "042700.KQ"]


def test_filter_by_mode_invalid_raises():
    with pytest.raises(ValueError):
        _filter_by_mode(["NVDA"], "midday")


def test_news_section_skips_empty_tickers():
    out = _news_section({
        "NVDA": [{"title": "Nvidia rally on AI demand", "publisher": "CNBC"}],
        "AAOI": [],
        "AMD": [{"title": "AMD beats Q1", "publisher": "Reuters"}],
    })
    assert "### NVDA" in out
    assert "(CNBC) Nvidia rally on AI demand" in out
    assert "### AAOI" not in out
    assert "### AMD" in out
    assert "(Reuters) AMD beats Q1" in out


def test_main_e2e_with_mocks(monkeypatch, tmp_path):
    """Wires data_fetcher → analyze → fetch_headlines → call_agent → file write."""
    fake_df = pd.DataFrame({
        "close": [100.0, 50.0],
        "prev_close": [90.0, 55.0],
        "change_pct": [11.11, -9.09],
        "volume": [1000, 500],
        "ma5": [95, 52],
        "ma20": [85, 60],
        "vol_avg20": [800, 600],
        "volatility20": [3.0, 4.0],
    }, index=["NVDA", "AAOI"])
    fake_df.index.name = "ticker"

    captured = {}

    def fake_fetch_quotes(tickers, today=None):
        captured["tickers"] = tickers
        return fake_df

    def fake_fetch_headlines(tickers, ontology, per_ticker=3):
        captured["news_tickers"] = tickers
        return {t: [{"title": f"head-{t}", "publisher": "CNBC"}] for t in tickers}

    def fake_call_agent(name, user_input, model="gpt-4o-mini"):
        captured["agent_name"] = name
        captured["agent_input"] = user_input
        return "## Report\nfake report body"

    monkeypatch.setattr(main, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(main, "fetch_headlines", fake_fetch_headlines)
    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    monkeypatch.setattr(main, "REPORTS_DIR", tmp_path)

    out = main.main("morning", top_n=2, per_ticker_news=1)

    assert out.exists()
    assert "fake report body" in out.read_text(encoding="utf-8")
    assert captured["agent_name"] == "stock-analyst"
    assert "mode=morning" in captured["agent_input"]
    assert "head-NVDA" in captured["agent_input"]
    assert "005930.KS" not in captured["tickers"]  # morning filtered out KR


def test_main_evening_filters_us(monkeypatch, tmp_path):
    captured = {}

    def fake_fetch_quotes(tickers, today=None):
        captured["tickers"] = tickers
        return pd.DataFrame()  # empty short-circuits

    monkeypatch.setattr(main, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(main, "REPORTS_DIR", tmp_path)

    result = main.main("evening")

    assert result is None
    assert all(_is_kr(t) for t in captured["tickers"])
