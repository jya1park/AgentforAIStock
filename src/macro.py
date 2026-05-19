"""Macro signal: VIX (fear gauge) for bubble/fear interpretation."""

import json
from datetime import date
from pathlib import Path

import yfinance as yf

CACHE_DIR = Path("/tmp")


def _interpret(vix: float) -> str:
    if vix < 13:
        return "안일 (very low fear, complacency)"
    if vix < 18:
        return "정상 (normal)"
    if vix < 25:
        return "긴장 (elevated)"
    if vix < 35:
        return "공포 (high fear)"
    return "패닉 (extreme fear)"


def fetch_vix(today: date | None = None) -> dict:
    """VIX latest + 7d change + interpretation. Empty dict on failure."""
    today = today or date.today()
    cache_path = CACHE_DIR / f"vix_{today.isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    try:
        hist = yf.Ticker("^VIX").history(period="7d")
    except Exception:
        return {}
    if hist.empty:
        return {}
    close = hist["Close"]
    current, prev = float(close.iloc[-1]), float(close.iloc[0])
    out = {
        "vix": round(current, 2),
        "vix_7d_change_pct": round((current / prev - 1) * 100, 2),
        "interpretation": _interpret(current),
    }
    cache_path.write_text(json.dumps(out))
    return out


def macro_block(vix_data: dict) -> str:
    if not vix_data:
        return "## Macro 시그널\n- VIX 데이터 없음\n"
    return (
        "## Macro 시그널 (시장 분위기)\n"
        f"- VIX: {vix_data['vix']:.2f} → {vix_data['interpretation']}\n"
        f"- VIX 7일 변동: {vix_data['vix_7d_change_pct']:+.2f}%\n"
    )
