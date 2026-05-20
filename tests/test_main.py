import pandas as pd
import pytest

from src import main
from src.main import _filter_by_mode, _is_kr, _news_section, _split_report


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


def test_split_report_extracts_both_fences():
    raw = "preamble\n```long_markdown\n# Daily Report\nbody text\n```\n\n```short_kakao\n핵심 한 줄\n```\ntrailer"
    long_b, short_b = _split_report(raw)
    assert long_b == "# Daily Report\nbody text"
    assert short_b == "핵심 한 줄"


def test_split_report_falls_back_when_no_fences():
    raw = "no fences here, just text"
    long_b, short_b = _split_report(raw)
    assert long_b == "no fences here, just text"
    assert short_b == ""


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

    captured = {"tickers": None}
    calls = []

    def fake_fetch_quotes(tickers, today=None):
        captured["tickers"] = tickers
        return fake_df

    def fake_fetch_headlines(tickers, ontology, per_ticker=3):
        return {t: [{"title": f"head-{t}", "publisher": "CNBC"}] for t in tickers}

    def fake_call_agent(name, user_input, model="gpt-4o-mini"):
        calls.append({"name": name, "input": user_input, "model": model})
        if name == "stock-analyst":
            return "```long_markdown\n## Report\nfake report body\n```\n```short_kakao\nNVDA AI 강세\n```"
        if name == "red-team":
            return "## 사실 정합성\n- head-NVDA: ✅ 일치\n- critical 환각: 없음"
        return ""

    monkeypatch.setattr(main, "fetch_quotes", fake_fetch_quotes)
    monkeypatch.setattr(main, "fetch_headlines", fake_fetch_headlines)
    monkeypatch.setattr(main, "fetch_vix",
                        lambda: {"vix": 14.5, "vix_7d_change_pct": -2.1, "interpretation": "정상 (13-18)"})
    monkeypatch.setattr(main, "fetch_yields",
                        lambda: {"y3m": 4.20, "y10y": 4.45, "y30y": 4.60,
                                 "y10y_7d_bp": -8.0, "y30y_7d_bp": -10.0,
                                 "spread_10y_3m_bp": 25.0, "curve": "평탄화 (0-50bp)"})
    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    monkeypatch.setattr(main, "REPORTS_DIR", tmp_path)

    out = main.main("morning", top_n=2, per_ticker_news=1)

    assert out.exists()
    assert out.read_text(encoding="utf-8") == "## Report\nfake report body"
    kakao = tmp_path / out.name.replace(".md", "_kakao.txt")
    assert kakao.read_text(encoding="utf-8") == "NVDA AI 강세"
    redteam = tmp_path / out.name.replace(".md", "_redteam.md")
    assert "사실 정합성" in redteam.read_text(encoding="utf-8")

    assert [c["name"] for c in calls] == ["stock-analyst", "red-team"]
    assert "mode=morning" in calls[0]["input"]
    assert "head-NVDA" in calls[0]["input"]
    assert "VIX: 14.50" in calls[0]["input"]  # vix signal injected
    assert "10Y: 4.45%" in calls[0]["input"]  # yields signal injected
    assert "+25.0bp" in calls[0]["input"]  # spread shown
    assert "# 입력 페이로드" in calls[1]["input"]
    assert "# 분석가 리포트" in calls[1]["input"]
    assert "fake report body" in calls[1]["input"]  # long_body passed to red-team
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
