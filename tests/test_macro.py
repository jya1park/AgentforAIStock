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


def _fg_response(payload):
    fake = MagicMock()
    fake.raise_for_status.return_value = None
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
    assert "Mozilla" in captured["headers"]["User-Agent"]


def test_fetch_fear_greed_korean_rating_mapping(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response({
        "fear_and_greed": {"score": 82, "rating": "extreme greed",
                           "previous_close": 80, "previous_1_week": 75,
                           "previous_1_month": 60, "previous_1_year": 40}
    }))
    assert fetch_fear_greed()["rating_kr"] == "극단적 탐욕"


def test_fetch_fear_greed_returns_empty_on_network_error(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    def boom(*a, **kw): raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", boom)
    assert fetch_fear_greed() == {}


def test_fetch_fear_greed_returns_empty_on_missing_score(monkeypatch, tmp_path):
    monkeypatch.setattr(macro, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fg_response({"fear_and_greed": {}}))
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
