"""설정 파일을 검사하고 현재 적용될 관심사를 출력한다."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import AlertConfig, load_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Research Alert 설정 검사")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/keywords.yaml"),
        help="YAML 설정 파일 경로 (기본값: config/keywords.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except ValueError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 1

    _print_summary(config)
    return 0


def _print_summary(config: AlertConfig) -> None:
    print("설정이 유효합니다.")
    print(f"- 포함(하나 이상): {', '.join(config.include_any) or '없음'}")
    print(f"- 포함(모두): {', '.join(config.include_all) or '없음'}")
    print(f"- 제외: {', '.join(config.exclude) or '없음'}")
    print(f"- 최대 전송: {config.max_papers}편 / 최근 {config.lookback_hours}시간")
    print(f"- 제외 저널: {', '.join(config.excluded_journals) or '없음'}")
    print(f"- 제외 출판사: {', '.join(config.excluded_publishers) or '없음'}")
    print(f"- Tier 외 저널 허용: {'예' if config.allow_unlisted_journals else '아니오'}")
    print(f"- Nature RSS 피드: {len(config.rss_feeds)}개")
    for tier, journals in config.journal_tiers.items():
        print(f"- {tier}: {', '.join(journals) or '없음'}")


if __name__ == "__main__":
    raise SystemExit(main())
