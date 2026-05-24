"""Append daily segment rollup to JSON for trend charting."""

import json
from datetime import date
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "data" / "segment_history.json"


def _load() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def append(day: date, segments: list[dict]) -> None:
    """Save one day's segment rollup. segments = [{"segment": ..., "avg_change_pct": ...}, ...]."""
    history = _load()
    history[day.isoformat()] = {s["segment"]: s["avg_change_pct"] for s in segments}
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def load_recent(days: int = 14) -> dict[str, dict[str, float]]:
    """Return last N days sorted by date. {date_str: {segment: pct}}."""
    history = _load()
    sorted_dates = sorted(history.keys())[-days:]
    return {d: history[d] for d in sorted_dates}
