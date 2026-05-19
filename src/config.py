"""Auto-load .env on import and expose required env vars as module attrs."""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY")
