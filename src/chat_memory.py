"""Persist last N turns per chat_id as JSON. Single-user MVP, file-based."""

import json
from pathlib import Path

MEMORY_PATH = Path(__file__).resolve().parent.parent / "data" / "chat_history.json"
MAX_TURNS = 10  # user msgs + assistant msgs = 2 * MAX_TURNS messages


def _read_all() -> dict:
    if not MEMORY_PATH.exists():
        return {}
    try:
        return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_all(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load(chat_id: str) -> list[dict]:
    """Return chat_id's recent turns as OpenAI messages, [] if none."""
    return _read_all().get(chat_id, [])


def append(chat_id: str, user: str, assistant: str) -> None:
    """Append one turn; truncate to last MAX_TURNS pairs."""
    data = _read_all()
    history = data.get(chat_id, [])
    history.append({"role": "user", "content": user})
    history.append({"role": "assistant", "content": assistant})
    data[chat_id] = history[-2 * MAX_TURNS:]
    _write_all(data)


def clear(chat_id: str) -> None:
    data = _read_all()
    if chat_id in data:
        del data[chat_id]
        _write_all(data)
