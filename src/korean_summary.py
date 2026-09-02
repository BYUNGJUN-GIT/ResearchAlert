"""Gemini API로 논문 초록을 읽고 자연스러운 한국어 핵심 문장을 생성한다."""

from __future__ import annotations

from dataclasses import replace
import re
import time
from typing import Any, Iterable

from google import genai


# Gemini 무료 티어의 분당 생성 요청 한도(현재 5회)를 넘지 않도록 여유를 둔다.
REQUEST_INTERVAL_SECONDS = 13
MAX_RATE_LIMIT_RETRIES = 3


def summarize_in_korean(papers: Iterable[Any], api_key: str) -> list[Any]:
    """논문별 제목·초록 전체를 읽고 한 문장 한국어 핵심 요약을 생성한다."""
    client = genai.Client(api_key=api_key)
    summarized: list[Any] = []
    for index, paper in enumerate(papers):
        if index:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        summary_ko = _generate_summary(client, paper)
        if not summary_ko:
            raise RuntimeError(f"한국어 요약 생성 실패 ({paper.title}): 빈 응답")
        summarized.append(replace(paper, summary_ko=summary_ko))
    return summarized


def _generate_summary(client: Any, paper: Any) -> str:
    """무료 티어의 일시적인 429는 서버가 제시한 대기 시간 후 재시도한다."""
    prompt = (
        "다음 논문의 제목과 초록 전체를 읽고, 연구의 핵심 방법 또는 대상과 가장 중요한 결과를 "
        "자연스럽고 정확한 학술 한국어 한 문장으로 요약하세요. 초록 문장을 그대로 번역하거나 "
        "이어 붙이지 말고 내용을 압축해 새 문장으로 작성하세요. 원문에 없는 해석, 수치, "
        "인과관계는 추가하지 말고 전문 용어와 단위는 정확히 보존하세요. 요약문만 출력하세요.\n\n"
        f"제목: {paper.title}\n\n초록: {paper.abstract}"
    )
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            response = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
            return (response.text or "").strip()
        except Exception as error:
            if "429" not in str(error) or attempt == MAX_RATE_LIMIT_RETRIES:
                raise RuntimeError(f"한국어 요약 생성 실패 ({paper.title}): {error}") from error
            delay = _retry_delay_seconds(str(error))
            print(f"Gemini 무료 한도 도달: {delay}초 후 요약 요청을 재시도합니다.")
            time.sleep(delay)
    return ""  # 반복문 분석을 위한 방어 코드


def _retry_delay_seconds(message: str) -> int:
    """Gemini 오류의 retryDelay(예: '44s')를 읽고, 없으면 안전한 기본값을 쓴다."""
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)s", message)
    return max(15, int(match.group(1)) + 2) if match else 60
