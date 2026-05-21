"""Telegram Bot API sender — one-way notification of daily reports."""

import os

import requests

from src import config  # noqa: F401 — triggers .env autoload

_TELEGRAM_LIMIT = 4096


def _split_for_telegram(text: str, limit: int = _TELEGRAM_LIMIT) -> list[str]:
    """Split text into chunks ≤ limit, preferring paragraph then line boundaries."""
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = remaining.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def send_message(text: str, chat_id: str | None = None, bot_token: str | None = None) -> bool:
    """POST to Bot API sendMessage, splitting at 4096 chars. False on missing creds or any failure."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    for chunk in _split_for_telegram(text):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": chunk},
                timeout=10,
            )
            r.raise_for_status()
        except requests.RequestException:
            return False
    return True
