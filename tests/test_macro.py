from unittest.mock import MagicMock

import pandas as pd
import pytest
import requests

from src import macro
from src.macro import (
    _interpret, _interpret_curve, fetch_fear_greed, fetch_vix, fetch_yields,
    macro_block, yields_block,
)


def test_interpret_thresholds():
    assert "안일" in _interpret(10)
    assert "정상" in _interpret(15)
    assert "긴장" in _interpret(22)
    assert "공포" in _interpret(30)
    assert "패닉" in _interpret(40)


def test_fetch_vix_parses_history(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame(
        {"Close": [18.0, 19.0, 17.5, 16.0, 15.5]},
        index=pd.date_range("2026-05-12", periods=5),
    )
    monkeypatch.setattr(macro.yf, "Ticker", lambda t: fake_ticker)
    r = fetch_vix()
    assert r["vix"] == 15.5
    assert r["vix_7d_change_pct"] == pytest.approx(round((15.5 / 18.0 - 1) * 100, 2))
    assert "정상" in r["interpretation"]


def test_fetch_vix_caches_per_day(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def make_ticker(t):
        calls["n"] += 1
        m = MagicMock()
        m.history.return_value = pd.DataFrame({"Close": [20.0, 22.0]})
        return m

    monkeypatch.setattr(macro.yf, "Ticker", make_ticker)
    fetch_vix()
    fetch_vix()
    assert calls["n"] == 1  # second call hit cache


def test_fetch_vix_returns_empty_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    def boom(t): raise RuntimeError("network")
    monkeypatch.setattr(macro.yf, "Ticker", boom)
    assert fetch_vix() == {}


def test_macro_block_renders_or_skips():
    out = macro_block({"vix": 14.5, "vix_7d_change_pct": -2.1, "interpretation": "정상 (13-18)"})
    assert "VIX: 14.50" in out
    assert "정상 (13-18)" in out
    assert "VIX 7일 변동: -2.10%" in out
    assert "임계 가이드" in out
    assert "안일 <13" in out

    empty = macro_block({})
    assert "데이터 없음" in empty


def test_interpret_includes_range_string():
    assert "<13" in _interpret(10)
    assert "13-18" in _interpret(15)
    assert "18-25" in _interpret(22)
    assert "25-35" in _interpret(30)
    assert "≥35" in _interpret(40)


def test_interpret_curve_thresholds():
    assert "역수익률" in _interpret_curve(-10)
    assert "평탄화" in _interpret_curve(25)
    assert "정상 우상향" in _interpret_curve(80)
    assert "급경사" in _interpret_curve(200)


def test_fetch_yields_parses_three_tickers(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)

    closes = {"^IRX": [4.10, 4.20], "^TNX": [4.50, 4.45], "^TYX": [4.70, 4.60]}

    def make_ticker(sym):
        m = MagicMock()
        m.history.return_value = pd.DataFrame({"Close": closes[sym]})
        return m

    monkeypatch.setattr(macro.yf, "Ticker", make_ticker)
    r = fetch_yields()
    assert r["y3m"] == 4.20
    assert r["y10y"] == 4.45
    assert r["y30y"] == 4.60
    assert r["y10y_7d_bp"] == -5.0  # (4.45 - 4.50) * 100
    assert r["spread_10y_3m_bp"] == round((4.45 - 4.20) * 100, 1)  # 25.0
    assert "평탄화" in r["curve"]


def test_fetch_yields_skips_failed_tickers(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)

    def make_ticker(sym):
        m = MagicMock()
        if sym == "^TYX":
            m.history.return_value = pd.DataFrame()  # 30Y unavailable
        else:
            m.history.return_value = pd.DataFrame({"Close": [4.0, 4.2]})
        return m

    monkeypatch.setattr(macro.yf, "Ticker", make_ticker)
    r = fetch_yields()
    assert "y30y" not in r
    assert "y10y" in r and "y3m" in r
    assert "spread_10y_3m_bp" in r


def test_yields_block_renders_levels_spread_changes():
    y = {
        "y3m": 4.20, "y3m_7d_bp": 5.0,
        "y10y": 4.45, "y10y_7d_bp": -8.0,
        "y30y": 4.60, "y30y_7d_bp": -10.0,
        "spread_10y_3m_bp": 25.0,
        "curve": "평탄화 (0-50bp) — 경기 둔화 우려",
    }
    out = yields_block(y)
    assert "3M: 4.20%" in out
    assert "10Y: 4.45%" in out
    assert "30Y: 4.60%" in out
    assert "+25.0bp" in out
    assert "평탄화" in out
    assert "10Y -8.0bp" in out and "30Y -10.0bp" in out
    assert "곡선 가이드" in out


def test_yields_block_empty():
    assert "데이터 없음" in yields_block({})


def _fg_response(payload, status_code=200, text=""):
    fake = MagicMock()
    fake.status_code = status_code
    fake.text = text or (str(payload) if payload else "")
    fake.json.return_value = payload
    return fake


def test_fetch_fear_greed_happy_path(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    captured = {}
    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        return _fg_response({
            "fear_and_greed": {
                "score": 45.34,
                "rating": "neutral",
                "previous_close": 47.1,
                "previous_1_week": 52.4,
                "previous_1_month": 38.9,
                "previous_1_year": 60.2,
            }
        })
    monkeypatch.setattr(requests, "get", fake_get)
    out = fetch_fear_greed()
    assert out["score"] == 45.3
    assert out["rating"] == "neutral"
    assert out["rating_kr"] == "중립"
    assert out["previous_1_month"] == 38.9


def test_fetch_fear_greed_sends_full_browser_headers(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    captured = {}
    def fake_get(url, headers, timeout):
        captured["headers"] = headers
        return _fg_response({"fear_and_greed": {"score": 50, "rating": "neutral"}})
    monkeypatch.setattr(requests, "get", fake_get)
    fetch_fear_greed()
    assert "Chrome" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Accept"] == "application/json, text/plain, */*"
    assert captured["headers"]["Origin"] == "https://www.cnn.com"
    assert captured["headers"]["Referer"] == "https://www.cnn.com/"


def test_fetch_fear_greed_korean_rating_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response({
        "fear_and_greed": {"score": 82, "rating": "extreme greed",
                           "previous_close": 80, "previous_1_week": 75,
                           "previous_1_month": 60, "previous_1_year": 40}
    }))
    assert fetch_fear_greed()["rating_kr"] == "극단적 탐욕"


def test_fetch_fear_greed_falls_back_to_historical_when_snapshot_missing(monkeypatch, tmp_path):
    """If CNN drops the 'fear_and_greed' snapshot field, use the latest historical point."""
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    # 30-day series; latest is the last entry
    hist = [{"x": 1700000000000 + i * 86400000, "y": 30.0 + i, "rating": "fear"} for i in range(30)]
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response({
        "fear_and_greed_historical": {"data": hist}
    }))
    out = fetch_fear_greed()
    assert out["score"] == 59.0  # 30 + 29
    assert out["rating"] == "fear"
    assert out["previous_close"] == 58.0  # second-to-last
    assert out["previous_1_week"] == 54.0  # data[-6]
    assert out["previous_1_month"] == 39.0  # data[-21]


def test_fetch_fear_greed_returns_empty_on_network_error(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    def boom(*a, **kw): raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    assert fetch_fear_greed() == {}


def test_fetch_fear_greed_returns_empty_on_http_403(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response(None, status_code=403, text="Host not in allowlist"))
    assert fetch_fear_greed() == {}
    assert "HTTP 403" in capsys.readouterr().out


def test_fetch_fear_greed_returns_empty_when_no_snapshot_or_historical(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response({"unrelated": "shape"}))
    assert fetch_fear_greed() == {}


def test_fetch_fear_greed_uses_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    call_count = {"n": 0}
    def counting_get(*a, **kw):
        call_count["n"] += 1
        return _fg_response({
            "fear_and_greed": {"score": 50, "rating": "neutral",
                               "previous_close": 48, "previous_1_week": 45,
                               "previous_1_month": 40, "previous_1_year": 55}
        })
    monkeypatch.setattr(requests, "get", counting_get)
    fetch_fear_greed()
    fetch_fear_greed()  # second call should hit the disk cache
    assert call_count["n"] == 1


def test_fear_greed_block_renders_score_rating_trend():
    fg = {"score": 62.0, "rating": "greed", "rating_kr": "탐욕",
          "previous_close": 58.0, "previous_1_week": 55.0,
          "previous_1_month": 42.0, "previous_1_year": 50.0}
    out = macro.fear_greed_block(fg)
    assert "Fear & Greed Index" in out
    assert "62.0 → 탐욕" in out
    assert "탐욕 (55-75)" in out  # bucket label
    assert "전일 58.0" in out
    assert "1주 전 55.0" in out
    assert "1개월 전 42.0" in out
    assert "1년 전 50.0" in out
    assert "구간 가이드" in out


def test_fear_greed_block_skips_missing_trend_fields():
    fg = {"score": 30.0, "rating": "fear", "rating_kr": "공포",
          "previous_close": 32.0,
          "previous_1_week": None, "previous_1_month": None, "previous_1_year": None}
    out = macro.fear_greed_block(fg)
    assert "전일 32.0" in out
    assert "1주 전" not in out
    assert "1개월 전" not in out


def test_fear_greed_block_empty():
    assert "데이터 없음" in macro.fear_greed_block({})


def test_fear_greed_interpret_thresholds():
    assert "극단적 공포" in macro._fg_interpret(10)
    assert "공포 (25-45)" in macro._fg_interpret(30)
    assert "중립" in macro._fg_interpret(50)
    assert "탐욕 (55-75)" in macro._fg_interpret(65)
    assert "극단적 탐욕" in macro._fg_interpret(80)


def test_interpret_breadth_broad():
    assert "broad" in macro._interpret_breadth(spread_pp=2.0, market_pct=1.5)
    assert "broad" in macro._interpret_breadth(spread_pp=-2.5, market_pct=-1.0)


def test_interpret_breadth_narrow_rally_market_down():
    """Tech up while market down — the bubble-entry signal."""
    out = macro._interpret_breadth(spread_pp=5.0, market_pct=-2.0)
    assert "narrow rally" in out
    assert "기술 강세" in out
    assert "거품 진입" in out or "과열" in out


def test_interpret_breadth_extreme_narrow_market_down():
    out = macro._interpret_breadth(spread_pp=8.5, market_pct=-1.5)
    assert "extreme narrow" in out


def test_interpret_breadth_tech_lagging_market_rising():
    """Market up while tech down — money rotation away from tech."""
    out = macro._interpret_breadth(spread_pp=-4.0, market_pct=2.0)
    assert "기술 약세" in out
    assert "차익실현" in out or "자금 이동" in out


def test_fetch_breadth_computes_5d_and_20d(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    # Build 25-day series; index -1 is today, -6 is 5d ago, -21 is 20d ago
    soxx_closes = [100 + i * 0.5 for i in range(25)]  # gentle upward
    soxx_closes[-1] = 115.0  # final pop → 5d/20d both positive
    spy_closes = [400 + i * -0.2 for i in range(25)]
    spy_closes[-1] = 392.0

    def make_ticker(sym):
        m = MagicMock()
        closes = soxx_closes if sym == "SOXX" else spy_closes
        m.history.return_value = pd.DataFrame({"Close": closes})
        return m
    monkeypatch.setattr(macro.yf, "Ticker", make_ticker)

    out = macro.fetch_breadth()
    assert "tech_5d_pct" in out and "market_5d_pct" in out
    assert "spread_5d_pp" in out and "spread_20d_pp" in out
    assert out["spread_5d_pp"] == round(out["tech_5d_pct"] - out["market_5d_pct"], 2)
    assert "interpretation" in out


def test_fetch_breadth_returns_empty_on_short_history(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    m = MagicMock()
    m.history.return_value = pd.DataFrame({"Close": [100.0, 101.0]})  # only 2 days
    monkeypatch.setattr(macro.yf, "Ticker", lambda s: m)
    assert macro.fetch_breadth() == {}


def test_fetch_breadth_returns_empty_on_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    def boom(s): raise RuntimeError("net")
    monkeypatch.setattr(macro.yf, "Ticker", boom)
    assert macro.fetch_breadth() == {}


def test_fetch_breadth_caches_per_day(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    calls = {"n": 0}
    closes = [100 + i for i in range(25)]
    def make_ticker(s):
        calls["n"] += 1
        m = MagicMock()
        m.history.return_value = pd.DataFrame({"Close": closes})
        return m
    monkeypatch.setattr(macro.yf, "Ticker", make_ticker)
    macro.fetch_breadth()
    macro.fetch_breadth()
    assert calls["n"] == 2  # 2 tickers fetched once; second call hits cache


def test_breadth_block_renders_5d_20d_spread_interpretation():
    b = {
        "tech_5d_pct": 5.20, "market_5d_pct": -2.10, "spread_5d_pp": 7.30,
        "tech_20d_pct": 12.40, "market_20d_pct": 1.80, "spread_20d_pp": 10.60,
        "interpretation": "extreme narrow rally (기술 강세) — 시장 전반 약세 + 자금 기술주 집중, 과열 진입 시그널",
    }
    out = macro.breadth_block(b)
    assert "시장 폭" in out
    assert "SOXX" in out and "+5.20%" in out
    assert "SPY" in out and "-2.10%" in out
    assert "+7.30%p" in out
    assert "20일" in out
    assert "extreme narrow" in out
    assert "가이드" in out


def test_breadth_block_empty():
    assert "데이터 없음" in macro.breadth_block({})
