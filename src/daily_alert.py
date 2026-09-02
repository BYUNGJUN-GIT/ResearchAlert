"""수집 → 한국어 요약 → Telegram 전송을 하나로 실행한다."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from collect_papers import collect, print_results, write_results
from config import load_config
from korean_summary import summarize_in_korean
from telegram import send_digest


def main() -> int:
    parser = argparse.ArgumentParser(description="매일 Research Alert 실행")
    parser.add_argument("--config", type=Path, default=Path("config/keywords.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/latest_candidates.json"))
    parser.add_argument("--per-keyword", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="Telegram 전송 없이 후보만 확인")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        api_key = os.getenv("OPENALEX_API_KEY")
        if not api_key:
            raise RuntimeError("OPENALEX_API_KEY 환경 변수가 필요합니다. OpenAlex 무료 API 키를 설정하세요.")
        if args.per_keyword < 1 or args.per_keyword > 100 or args.max_pages < 1 or args.max_pages > 10:
            raise ValueError("--per-keyword는 1~100, --max-pages는 1~10 사이여야 합니다.")
        papers = collect(config, args.per_keyword, args.max_pages, api_key)
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY 환경 변수가 필요합니다. 한국어 요약을 위해 Gemini API 키를 설정하세요.")
        papers = summarize_in_korean(papers, gemini_api_key)
        write_results(papers, args.output)
        print_results(papers)
        if args.dry_run or not papers:
            return 0

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            raise RuntimeError("TELEGRAM_BOT_TOKEN 및 TELEGRAM_CHAT_ID 환경 변수가 필요합니다.")
        send_digest(papers, token, chat_id)
        print("\nTelegram 전송 완료")
        return 0
    except (RuntimeError, ValueError) as error:
        print(f"실행 오류: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
