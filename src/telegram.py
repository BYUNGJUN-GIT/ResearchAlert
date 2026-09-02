"""Telegram Bot API로 Research Alert 메시지를 전송한다."""

from __future__ import annotations

import html
import json
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def send_digest(papers: Iterable[Any], bot_token: str, chat_id: str) -> None:
    """논문 목록 전체를 전송한다. 하나라도 실패하면 예외를 발생시킨다."""
    messages = _format_messages(list(papers))
    for message in messages:
        _send_message(bot_token, chat_id, message)


def _format_messages(papers: list[Any]) -> list[str]:
    header = "<b>Research Alert</b>\n최근 7일 신규 논문 추천"
    blocks = [header]
    for number, paper in enumerate(papers, start=1):
        title = html.escape(paper.title)
        journal = html.escape(paper.journal or "저널 정보 없음")
        url = html.escape(paper.landing_page_url or paper.doi or paper.id, quote=True)
        keywords = html.escape(", ".join(paper.matched_keywords))
        summary = html.escape(paper.summary_ko or paper.summary)
        blocks.append(
            f"\n<b>{number}. [{paper.tier}]</b> <a href=\"{url}\">{title}</a>\n"
            f"{journal} | {paper.publication_date or '날짜 정보 없음'}\n"
            f"일치: {keywords}\n"
            f"핵심: {summary}"
        )

    messages: list[str] = []
    current = ""
    for block in blocks:
        # Telegram sendMessage의 텍스트 제한보다 여유 있게 나눠 HTML 태그가 깨지지 않게 한다.
        if current and len(current) + len(block) > 3800:
            messages.append(current)
            current = "<b>Research Alert (계속)</b>\n" + block
        else:
            current += block
    if current:
        messages.append(current)
    return messages


def _send_message(bot_token: str, chat_id: str, text: str) -> None:
    body = urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    request = Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except OSError as exc:
        raise RuntimeError(f"Telegram 전송 연결 실패: {exc}") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        description = payload.get("description", "알 수 없는 오류") if isinstance(payload, dict) else "잘못된 응답"
        raise RuntimeError(f"Telegram 전송 실패: {description}")
