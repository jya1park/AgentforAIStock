"""Telegram Bot API sender — one-way notification of daily reports."""

import os

import requests

from src import config  # noqa: F401 — triggers .env autoload


def send_message(text: str, chat_id: str | None = None, bot_token: str | None = None) -> bool:
    """POST to Bot API sendMessage. True on 200, False on missing creds or network error."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except requests.RequestException:
        return False
