"""Macro signal: VIX (fear gauge) for bubble/fear interpretation."""

import json
from datetime import date
from pathlib import Path

import requests
import yfinance as yf

CACHE_DIR = Path("/tmp")


def _interpret(vix: float) -> str:
    if vix < 13:
        return "안일 (<13)"
    if vix < 18:
        return "정상 (13-18)"
    if vix < 25:
        return "긴장 (18-25)"
    if vix < 35:
        return "공포 (25-35)"
    return "패닉 (≥35)"


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
        "- 임계 가이드: 안일 <13 / 정상 13-18 / 긴장 18-25 / 공포 25-35 / 패닉 ≥35\n"
    )


YIELD_TICKERS = {"y3m": "^IRX", "y10y": "^TNX", "y30y": "^TYX"}


def _interpret_curve(spread_bp: float) -> str:
    if spread_bp < 0:
        return "역수익률 곡선 (<0bp) — 경기 침체 선행 신호"
    if spread_bp < 50:
        return "평탄화 (0-50bp) — 경기 둔화 우려"
    if spread_bp < 150:
        return "정상 우상향 (50-150bp)"
    return "급경사 (>150bp) — 경기 회복/인플레 기대"


def fetch_yields(today: date | None = None) -> dict:
    """3M/10Y/30Y Treasury yields + 10Y-3M spread + 7d changes (bp).
    Cached per day. Partial returns OK — empty {} only if all fetches failed."""
    today = today or date.today()
    cache_path = CACHE_DIR / f"yields_{today.isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    out: dict = {}
    for key, sym in YIELD_TICKERS.items():
        try:
            hist = yf.Ticker(sym).history(period="7d")
        except Exception:
            continue
        if hist.empty:
            continue
        close = hist["Close"]
        latest, prev = float(close.iloc[-1]), float(close.iloc[0])
        out[key] = round(latest, 2)
        out[f"{key}_7d_bp"] = round((latest - prev) * 100, 1)

    if "y10y" in out and "y3m" in out:
        spread_bp = round((out["y10y"] - out["y3m"]) * 100, 1)
        out["spread_10y_3m_bp"] = spread_bp
        out["curve"] = _interpret_curve(spread_bp)

    if out:
        cache_path.write_text(json.dumps(out))
    return out


def yields_block(y: dict) -> str:
    if not y:
        return "### 국채 금리\n- 데이터 없음\n"
    lines = ["### 국채 금리 (선행 지표)"]
    levels = []
    if "y3m" in y: levels.append(f"3M: {y['y3m']:.2f}%")
    if "y10y" in y: levels.append(f"10Y: {y['y10y']:.2f}%")
    if "y30y" in y: levels.append(f"30Y: {y['y30y']:.2f}%")
    if levels:
        lines.append(f"- 현재 — {' / '.join(levels)}")
    if "spread_10y_3m_bp" in y:
        lines.append(f"- 10Y-3M 스프레드: {y['spread_10y_3m_bp']:+.1f}bp → {y['curve']}")
    changes = []
    if "y10y_7d_bp" in y: changes.append(f"10Y {y['y10y_7d_bp']:+.1f}bp")
    if "y30y_7d_bp" in y: changes.append(f"30Y {y['y30y_7d_bp']:+.1f}bp")
    if changes:
        lines.append(f"- 7일 변동 — {', '.join(changes)}")
    lines.append("- 곡선 가이드: 역곡선 <0bp / 평탄 0-50bp / 정상 50-150bp / 급경사 >150bp")
    return "\n".join(lines) + "\n"


_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_FG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.cnn.com",
    "Referer": "https://www.cnn.com/",
}
_FG_RATING_KR = {
    "extreme fear": "극단적 공포",
    "fear": "공포",
    "neutral": "중립",
    "greed": "탐욕",
    "extreme greed": "극단적 탐욕",
}


def _round_or_none(v) -> float | None:
    return round(float(v), 1) if v is not None else None


def fetch_fear_greed(today: date | None = None) -> dict:
    """CNN Fear & Greed Index — current 0-100 score, rating, and trend snapshot.
    Returns empty {} on network or schema error (unofficial endpoint can change).
    Prints diagnostic on failure so the operator can see why it fell through."""
    today = today or date.today()
    cache_path = CACHE_DIR / f"fear_greed_{today.isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    try:
        r = requests.get(_FG_URL, headers=_FG_HEADERS, timeout=10)
    except requests.RequestException as e:
        print(f"fear_greed: network error — {type(e).__name__}: {e}")
        return {}
    if r.status_code != 200:
        print(f"fear_greed: HTTP {r.status_code} — {r.text[:200]}")
        return {}
    try:
        body = r.json()
    except ValueError as e:
        print(f"fear_greed: JSON parse error — {e}; first 200 bytes: {r.text[:200]}")
        return {}

    fg = body.get("fear_and_greed") or {}
    if "score" not in fg:
        hist = (body.get("fear_and_greed_historical") or {})
        data = hist.get("data") or []
        latest = data[-1] if data else None
        if latest and "y" in latest:
            fg = {
                "score": latest["y"],
                "rating": latest.get("rating", hist.get("rating", "")),
                "previous_close": data[-2]["y"] if len(data) >= 2 else None,
                "previous_1_week": data[-6]["y"] if len(data) >= 6 else None,
                "previous_1_month": data[-21]["y"] if len(data) >= 21 else None,
                "previous_1_year": data[0]["y"] if len(data) >= 250 else None,
            }
        else:
            print(f"fear_greed: schema mismatch — top-level keys: {list(body.keys())[:5]}")
            return {}

    rating = (fg.get("rating") or "").lower()
    out = {
        "score": round(float(fg["score"]), 1),
        "rating": rating,
        "rating_kr": _FG_RATING_KR.get(rating, rating),
        "previous_close": _round_or_none(fg.get("previous_close")),
        "previous_1_week": _round_or_none(fg.get("previous_1_week")),
        "previous_1_month": _round_or_none(fg.get("previous_1_month")),
        "previous_1_year": _round_or_none(fg.get("previous_1_year")),
    }
    cache_path.write_text(json.dumps(out))
    return out
