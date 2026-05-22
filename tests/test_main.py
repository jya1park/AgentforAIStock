from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src import main
from src.main import _extract_long_body, _filter_by_mode, _is_kr, _news_section, _thesis_block


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


def test_extract_long_body_strips_fence():
    raw = "preamble\n```long_markdown\n# Daily Report\nbody text\n```\ntrailer"
    assert _extract_long_body(raw) == "# Daily Report\nbody text"


def test_extract_long_body_falls_back_when_no_fence():
    assert _extract_long_body("no fences here, just text") == "no fences here, just text"


def test_thesis_block_renders_entries():
    out = _thesis_block([
        {"path": "hardware.ai_dc_operator", "thesis": "capex 700B"},
        {"path": "emerging_compute", "thesis": "역상관 시그널"},
    ])
    assert "도메인 thesis" in out
    assert "**hardware.ai_dc_operator**" in out
    assert "capex 700B" in out
    assert "**emerging_compute**" in out


def test_thesis_block_empty_returns_empty_string():
    assert _thesis_block([]) == ""


def test_news_section_skips_empty_tickers():
    now = datetime(2026, 5, 21, 12, tzinfo=timezone.utc)
    out = _news_section({
        "NVDA": [{"title": "Nvidia rally on AI demand", "publisher": "CNBC",
                  "published_at": now - timedelta(hours=2)}],
        "AAOI": [],
        "AMD": [{"title": "AMD beats Q1", "publisher": "Reuters",
                 "published_at": now - timedelta(hours=5)}],
    }, now=now)
    assert "### NVDA" in out
    assert "(CNBC, 2h ago) Nvidia rally on AI demand" in out
    assert "### AAOI" not in out
    assert "### AMD" in out
    assert "(Reuters, 5h ago) AMD beats Q1" in out


def test_news_section_drops_stale_and_undated():
    now = datetime(2026, 5, 21, 12, tzinfo=timezone.utc)
    out = _news_section({
        "NVDA": [
            {"title": "fresh", "publisher": "CNBC", "published_at": now - timedelta(hours=10)},
            {"title": "stale", "publisher": "CNBC", "published_at": now - timedelta(hours=120)},
            {"title": "undated", "publisher": "CNBC"},
            {"title": "no_parse", "publisher": "CNBC", "published_at": None},
        ],
    }, now=now)
    assert "fresh" in out
    assert "stale" not in out
    assert "undated" not in out
    assert "no_parse" not in out


def test_news_section_sorts_newest_first():
    now = datetime(2026, 5, 21, 12, tzinfo=timezone.utc)
    out = _news_section({
        "NVDA": [
            {"title": "older", "publisher": "CNBC", "published_at": now - timedelta(hours=20)},
            {"title": "newest", "publisher": "CNBC", "published_at": now - timedelta(hours=1)},
            {"title": "middle", "publisher": "CNBC", "published_at": now - timedelta(hours=8)},
        ],
    }, now=now)
    assert out.index("newest") < out.index("middle") < out.index("older")


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
        recent = datetime.now(timezone.utc) - timedelta(hours=3)
        return {t: [{"title": f"head-{t}", "publisher": "CNBC", "published_at": recent}] for t in tickers}

    def fake_call_agent(name, user_input, model="gpt-4o-mini"):
        calls.append({"name": name, "input": user_input, "model": model})
        if name == "stock-analyst":
            return "```long_markdown\n## Report\nfake report body\n```"
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
    monkeypatch.setattr(main, "fetch_fear_greed",
                        lambda: {"score": 62.0, "rating": "greed", "rating_kr": "탐욕",
                                 "previous_close": 58.0, "previous_1_week": 55.0,
                                 "previous_1_month": 42.0, "previous_1_year": 50.0})
    monkeypatch.setattr(main, "fetch_breadth",
                        lambda: {"nasdaq_advances_1d": 72, "nasdaq_total_1d": 100, "nasdaq_advance_pct_1d": 72.0,
                                 "dow_advances_1d": 10, "dow_total_1d": 30, "dow_advance_pct_1d": 33.3,
                                 "nasdaq_advances_5d": 65, "nasdaq_total_5d": 100, "nasdaq_advance_pct_5d": 65.0,
                                 "dow_advances_5d": 11, "dow_total_5d": 30, "dow_advance_pct_5d": 36.7,
                                 "ad_spread_1d_pp": 38.7, "ad_spread_5d_pp": 28.3,
                                 "interpretation": "extreme narrow rally (기술 강세) — 거품 진입 시그널"})
    monkeypatch.setattr(main, "call_agent", fake_call_agent)
    monkeypatch.setattr(main, "REPORTS_DIR", tmp_path)
    telegram_calls = []
    monkeypatch.setattr(main, "send_message", lambda text: telegram_calls.append(text) or True)

    out = main.main("morning", top_n=2, per_ticker_news=1)

    assert out.exists()
    assert out.read_text(encoding="utf-8") == "## Report\nfake report body"
    redteam = tmp_path / out.name.replace(".md", "_redteam.md")
    assert "사실 정합성" in redteam.read_text(encoding="utf-8")

    assert [c["name"] for c in calls] == ["stock-analyst", "red-team"]
    assert "mode=morning" in calls[0]["input"]
    assert "head-NVDA" in calls[0]["input"]
    assert "VIX: 14.50" in calls[0]["input"]  # vix signal injected
    assert "10Y: 4.45%" in calls[0]["input"]  # yields signal injected
    assert "+25.0bp" in calls[0]["input"]  # spread shown
    assert "Fear & Greed Index" in calls[0]["input"]  # F&G block injected
    assert "62.0 → 탐욕" in calls[0]["input"]  # current F&G value + Korean rating
    assert "1개월 전 42.0" in calls[0]["input"]  # F&G trend shown
    assert "시장 폭" in calls[0]["input"]  # breadth block injected
    assert "나스닥 100" in calls[0]["input"] and "72.0%" in calls[0]["input"]  # nasdaq advance leg
    assert "다우 30" in calls[0]["input"] and "33.3%" in calls[0]["input"]  # dow advance leg
    assert "+38.7%p" in calls[0]["input"]  # 1d A/D spread shown
    assert "도메인 thesis" in calls[0]["input"]  # ontology thesis injected
    assert "hardware.ai_dc_operator" in calls[0]["input"]
    assert "# 입력 페이로드" in calls[1]["input"]
    assert "# 분석가 리포트" in calls[1]["input"]
    assert "fake report body" in calls[1]["input"]  # long_body passed to red-team
    assert "005930.KS" not in captured["tickers"]  # morning filtered out KR
    assert telegram_calls == ["## Report\nfake report body"]  # long_body sent to telegram


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
