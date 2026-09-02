"""Telegram Bot이 최근 메시지를 받은 채팅 ID를 표시하는 초기 설정 도구."""

from __future__ import annotations

import json
import os
import sys
from urllib.request import Request, urlopen


def main() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN 환경 변수가 필요합니다.", file=sys.stderr)
        return 1

    request = Request(f"https://api.telegram.org/bot{token}/getUpdates")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except OSError as error:
        print(f"Telegram 연결 실패: {error}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict) or not payload.get("ok"):
        print("Telegram getUpdates 요청이 실패했습니다.", file=sys.stderr)
        return 1
    chat_ids: set[str] = set()
    for update in payload.get("result", []):
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post")
        if isinstance(message, dict) and isinstance(message.get("chat"), dict):
            chat_id = message["chat"].get("id")
            if isinstance(chat_id, int):
                chat_ids.add(str(chat_id))

    if not chat_ids:
        print("채팅을 찾지 못했습니다. Telegram에서 봇에게 /start를 먼저 보내세요.", file=sys.stderr)
        return 1
    print("발견한 TELEGRAM_CHAT_ID:")
    for chat_id in sorted(chat_ids):
        print(chat_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
