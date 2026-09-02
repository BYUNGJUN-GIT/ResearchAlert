"""Research Alert 설정을 읽고 검증하는 공통 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AlertConfig:
    include_any: tuple[str, ...]
    include_all: tuple[str, ...]
    exclude: tuple[str, ...]
    journal_tiers: dict[str, tuple[str, ...]]
    rss_feeds: tuple["JournalFeed", ...]
    excluded_journals: tuple[str, ...]
    excluded_publishers: tuple[str, ...]
    allow_unlisted_journals: bool
    max_papers: int
    language: str
    lookback_hours: int


@dataclass(frozen=True)
class JournalFeed:
    journal: str
    url: str


def load_config(path: str | Path) -> AlertConfig:
    """YAML 설정 파일을 읽고, 잘못된 값이면 ValueError를 발생시킨다."""
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"설정 파일을 찾을 수 없습니다: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML 형식이 올바르지 않습니다: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("설정 파일의 최상위 값은 객체여야 합니다.")

    keywords = _required_mapping(raw, "keywords")
    journals = _required_mapping(raw, "journals")
    delivery = _required_mapping(raw, "delivery")
    collection = _required_mapping(raw, "collection")
    journal_policy = _required_mapping(raw, "journal_policy")

    include_any = _string_list(keywords, "include_any")
    include_all = _string_list(keywords, "include_all")
    exclude = _string_list(keywords, "exclude")
    if not include_any and not include_all:
        raise ValueError("keywords.include_any 또는 keywords.include_all에 키워드를 하나 이상 넣으세요.")

    journal_tiers = {
        tier: tuple(_string_list(journals, tier))
        for tier in ("tier_1", "tier_2", "tier_3", "tier_4")
    }
    _ensure_unique_journals(journal_tiers)
    rss_feeds = _journal_feeds(raw)
    excluded_journals = tuple(_string_list(raw, "excluded_journals"))
    excluded_publishers = tuple(_string_list(raw, "excluded_publishers"))

    max_papers = _positive_int(delivery, "max_papers")
    language = _required_string(delivery, "language")
    if language not in {"ko", "en"}:
        raise ValueError("delivery.language는 'ko' 또는 'en'이어야 합니다.")

    return AlertConfig(
        include_any=tuple(include_any),
        include_all=tuple(include_all),
        exclude=tuple(exclude),
        journal_tiers=journal_tiers,
        rss_feeds=rss_feeds,
        excluded_journals=excluded_journals,
        excluded_publishers=excluded_publishers,
        allow_unlisted_journals=_required_bool(journal_policy, "allow_unlisted_journals"),
        max_papers=max_papers,
        language=language,
        lookback_hours=_positive_int(collection, "lookback_hours"),
    )


def _required_mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"'{key}' 항목은 객체여야 합니다.")
    return item


def _journal_feeds(value: dict[str, Any]) -> tuple[JournalFeed, ...]:
    feeds = value.get("rss_feeds")
    if not isinstance(feeds, list):
        raise ValueError("'rss_feeds' 항목은 목록이어야 합니다.")
    parsed: list[JournalFeed] = []
    for feed in feeds:
        if not isinstance(feed, dict):
            raise ValueError("rss_feeds의 각 항목은 객체여야 합니다.")
        journal = _required_string(feed, "journal")
        url = _required_string(feed, "url")
        if not url.startswith("https://"):
            raise ValueError("rss_feeds.url은 https URL이어야 합니다.")
        parsed.append(JournalFeed(journal=journal, url=url))
    return tuple(parsed)


def _string_list(value: dict[str, Any], key: str) -> list[str]:
    item = value.get(key)
    if not isinstance(item, list) or not all(isinstance(word, str) and word.strip() for word in item):
        raise ValueError(f"'{key}' 항목은 비어 있지 않은 문자열 목록이어야 합니다.")
    normalized = [word.strip() for word in item]
    if len({word.casefold() for word in normalized}) != len(normalized):
        raise ValueError(f"'{key}'에 중복된 키워드가 있습니다.")
    return normalized


def _required_string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"'{key}' 항목은 비어 있지 않은 문자열이어야 합니다.")
    return item.strip()


def _positive_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < 1:
        raise ValueError(f"'{key}' 항목은 1 이상의 정수여야 합니다.")
    return item


def _required_bool(value: dict[str, Any], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"'{key}' 항목은 true 또는 false여야 합니다.")
    return item


def _ensure_unique_journals(journal_tiers: dict[str, tuple[str, ...]]) -> None:
    journals = [journal for tier in journal_tiers.values() for journal in tier]
    if len({journal.casefold() for journal in journals}) != len(journals):
        raise ValueError("저널은 하나의 tier에만 한 번씩 넣으세요.")
