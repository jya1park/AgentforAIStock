from unittest.mock import MagicMock

import pandas as pd
import pytest

from src import macro
from src.macro import _interpret, fetch_vix, macro_block


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
    out = macro_block({"vix": 14.5, "vix_7d_change_pct": -2.1, "interpretation": "정상"})
    assert "VIX: 14.50" in out
    assert "정상" in out
    assert "VIX 7일 변동: -2.10%" in out

    empty = macro_block({})
    assert "데이터 없음" in empty
