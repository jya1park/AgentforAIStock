"""Long-poll Telegram for incoming messages and reply via GPT-4o.
Run: python -m src.telegram_bot  (keeps running until Ctrl+C)"""

import os
import sys
import time

from src import chat_memory, config  # noqa: F401 — triggers .env autoload
from src.chat_handler import ChatResult, answer
from src.telegram_notifier import get_updates, send_message, send_photo

WELCOME = (
    "안녕하세요. AI 산업 일일 리포트를 자동 송출하고, 이 채팅의 질문에 GPT-4o로 답변합니다.\n\n"
    "예시 질문:\n"
    "- 오늘 POET 왜 떨어졌어?\n"
    "- MU PER 얼마야?\n"
    "- NVDA 최근 분기 매출 어땠어?\n"
    "- 오늘 Fear & Greed 지수 얼마야?\n"
    "- 기술주는 오르는데 S&P는 어때? (시장 폭)\n"
    "- HBM 캐파 병목 어디서 발생?\n\n"
    "직전 10턴 대화를 기억합니다. /reset 으로 대화 기록 초기화.\n\n"
    "참고용 분석만 제공합니다 — 투자 결정은 본인 책임."
)


def _allowed_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def handle_message(msg: dict) -> None:
    chat_id = str(msg.get("chat", {}).get("id", ""))
    if chat_id != _allowed_chat_id():
        print(f"ignored chat_id={chat_id} (not whitelisted)")
        return
    text = (msg.get("text") or "").strip()
    if not text:
        return
    if text in ("/start", "/help"):
        send_message(WELCOME, chat_id=chat_id)
        return
    if text == "/reset":
        chat_memory.clear(chat_id)
        send_message("대화 기록을 초기화했습니다.", chat_id=chat_id)
        return
    print(f"q: {text}")
    history = chat_memory.load(chat_id)
    try:
        result = answer(text, history=history)
    except Exception as e:
        print(f"answer error: {e}")
        send_message("일시적 오류로 답변 생성 실패. 잠시 후 다시 시도해 주세요.", chat_id=chat_id)
        return
    if isinstance(result, ChatResult):
        send_message(result.text, chat_id=chat_id)
        for img in result.images:
            if img.exists():
                send_photo(img, chat_id=chat_id)
        chat_memory.append(chat_id, text, result.text)
        print(f"a: ({len(result.text)} chars, {len(result.images)} images, history={len(history) + 2})")
    else:
        send_message(result, chat_id=chat_id)
        chat_memory.append(chat_id, text, result)
        print(f"a: ({len(result)} chars, history={len(history) + 2})")


def main() -> None:
    if not _allowed_chat_id() or not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env", file=sys.stderr)
        sys.exit(1)
    print("telegram bot starting — long polling (Ctrl+C to stop)")
    offset: int | None = None
    backoff = 1
    while True:
        try:
            updates = get_updates(offset=offset, timeout=25)
            backoff = 1
            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("edited_message")
                if msg:
                    handle_message(msg)
        except KeyboardInterrupt:
            print("\nstopped by user")
            return
        except Exception as e:
            print(f"poll error: {e}, retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
