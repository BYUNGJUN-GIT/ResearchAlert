"""OpenAlex에서 신규 논문을 수집하고 Research Alert 설정으로 선별한다."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import AlertConfig, load_config
from nature_rss import fetch_rss_works
from publisher_abstract import fetch_public_abstract

OPENALEX_WORKS_URL = "https://api.openalex.org/works"
USER_AGENT = "ResearchAlert/0.1 (personal academic literature alert)"
# 34개 키워드와 상위 Tier 저널을 한 번에 조회하더라도 OpenAlex의 공유 API
# 한도에 걸리지 않도록 모든 OpenAlex 요청 사이에 간격을 둔다.
OPENALEX_REQUEST_INTERVAL_SECONDS = 2.2

# 응용 열관리 키워드는 넓게 잡히므로 낮은 가중치를 준다.
LOW_PRIORITY_KEYWORDS = {
    "thermal interface material",
    "thermal management",
    "heat dissipation",
    "semiconductor cooling",
    "semiconductor thermal management",
    "electronics cooling",
    "thermal packaging",
}


@dataclass(frozen=True)
class Paper:
    id: str
    doi: str | None
    title: str
    abstract: str
    publication_date: str | None
    journal: str | None
    publishers: tuple[str, ...]
    landing_page_url: str | None
    matched_keywords: tuple[str, ...]
    tier: str
    score: int
    keyword_score: int
    tier_score: int
    summary: str
    summary_ko: str | None = None


def fetch_recent_works(
    keyword: str, from_date: str, to_date: str, per_page: int, max_pages: int, api_key: str
) -> list[dict[str, Any]]:
    """OpenAlex에서 하나의 검색어에 맞는 최근 article 레코드를 가져온다."""
    all_results: list[dict[str, Any]] = []
    cursor = "*"
    for _ in range(max_pages):
        query = urlencode(
            {
                "search": keyword,
                "filter": f"from_publication_date:{from_date},to_publication_date:{to_date},type:article",
                "per_page": per_page,
                "sort": "publication_date:desc",
                "cursor": cursor,
                "api_key": api_key,
            }
        )
        request = Request(f"{OPENALEX_WORKS_URL}?{query}", headers={"User-Agent": USER_AGENT})
        payload = _request_with_retry(request, keyword)
        results = payload.get("results")
        if not isinstance(results, list):
            raise RuntimeError("OpenAlex 응답에 results 목록이 없습니다.")
        all_results.extend(item for item in results if isinstance(item, dict))
        meta = payload.get("meta")
        cursor = meta.get("next_cursor") if isinstance(meta, dict) else None
        if not cursor or not results:
            break
    return all_results


def _request_with_retry(request: Request, keyword: str) -> dict[str, Any]:
    for attempt in range(5):
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
            if isinstance(payload, dict):
                time.sleep(OPENALEX_REQUEST_INTERVAL_SECONDS)
                return payload
            raise RuntimeError("OpenAlex가 JSON 객체가 아닌 응답을 반환했습니다.")
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise RuntimeError(f"OpenAlex 요청 실패 (HTTP {exc.code}): {keyword}") from exc
            retry_after = exc.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            print(f"OpenAlex HTTP {exc.code}; {wait_seconds}초 후 재시도합니다.", file=sys.stderr)
            time.sleep(wait_seconds)
        except URLError as exc:
            if attempt == 4:
                raise RuntimeError(f"OpenAlex 연결 실패: {exc.reason}") from exc
            time.sleep(2**attempt)
    raise RuntimeError(f"OpenAlex 응답을 받지 못했습니다: {keyword}")


def resolve_source_id(journal: str, api_key: str) -> str | None:
    """저널명으로 OpenAlex Source ID를 찾아 정확히 일치하는 결과만 반환한다."""
    query = urlencode({"search": journal, "per_page": 10, "api_key": api_key})
    request = Request(f"https://api.openalex.org/sources?{query}", headers={"User-Agent": USER_AGENT})
    payload = _request_with_retry(request, f"source:{journal}")
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    for source in results:
        if isinstance(source, dict) and _normalize_for_matching(str(source.get("display_name") or "")) == _normalize_for_matching(journal):
            source_id = source.get("id")
            return str(source_id).rsplit("/", 1)[-1] if isinstance(source_id, str) else None
    return None


def fetch_source_works(source_id: str, from_date: str, to_date: str, api_key: str) -> list[dict[str, Any]]:
    """상위 Tier 저널의 최근 논문을 직접 조회해 광범위 키워드 검색의 누락을 막는다."""
    query = urlencode(
        {
            "filter": f"primary_location.source.id:{source_id},from_publication_date:{from_date},to_publication_date:{to_date},type:article",
            "per_page": 100,
            "sort": "publication_date:desc",
            "api_key": api_key,
        }
    )
    request = Request(f"{OPENALEX_WORKS_URL}?{query}", headers={"User-Agent": USER_AGENT})
    payload = _request_with_retry(request, f"source:{source_id}")
    results = payload.get("results")
    if not isinstance(results, list):
        raise RuntimeError("OpenAlex Source 응답에 results 목록이 없습니다.")
    return [item for item in results if isinstance(item, dict)]


def collect(config: AlertConfig, per_keyword: int, max_pages: int, api_key: str) -> list[Paper]:
    """설정 키워드로 수집하고 중복을 제거한 뒤, 점수 순으로 반환한다."""
    since = (datetime.now(UTC) - timedelta(hours=config.lookback_hours)).date().isoformat()
    today = datetime.now(UTC).date().isoformat()
    unique_works: dict[str, dict[str, Any]] = {}

    for index, keyword in enumerate(config.include_any, start=1):
        print(f"[{index}/{len(config.include_any)}] OpenAlex 검색: {keyword}", file=sys.stderr)
        for work in fetch_recent_works(keyword, since, today, per_keyword, max_pages, api_key):
            work_id = str(work.get("id") or work.get("doi") or "")
            if work_id:
                unique_works[work_id] = work
        # OpenAlex 공개 API에 짧은 간격을 두어 안정적으로 사용한다.
        time.sleep(0.1)

    # Tier 1·2 저널은 저널 단위로도 수집한다. 키워드 검색 결과가 많아도 상위 저널 신작을 놓치지 않는다.
    priority_journals = tuple(dict.fromkeys((*config.journal_tiers["tier_1"], *config.journal_tiers["tier_2"])))
    for index, journal in enumerate(priority_journals, start=1):
        print(f"[상위 Tier {index}/{len(priority_journals)}] OpenAlex 저널 검색: {journal}", file=sys.stderr)
        source_id = resolve_source_id(journal, api_key)
        if not source_id:
            print(f"OpenAlex Source를 찾지 못함: {journal}", file=sys.stderr)
            continue
        for work in fetch_source_works(source_id, since, today, api_key):
            work_id = str(work.get("id") or work.get("doi") or "")
            if work_id:
                unique_works[work_id] = work
        time.sleep(0.1)

    print(f"Nature RSS 검색: {len(config.rss_feeds)}개 피드", file=sys.stderr)
    for work in fetch_rss_works(config.rss_feeds, since):
        work_id = str(work.get("doi") or work.get("id") or "")
        if work_id:
            unique_works[work_id] = work

    papers = [_to_paper(work, config) for work in unique_works.values()]
    selected = [paper for paper in papers if paper is not None]
    return sorted(selected, key=lambda paper: (-paper.score, paper.publication_date or "", paper.title.casefold()))[
        : config.max_papers
    ]


def _to_paper(work: dict[str, Any], config: AlertConfig) -> Paper | None:
    title = str(work.get("title") or "").strip()
    abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
    if not title:
        return None

    # OpenAlex 초록이 없는 경우에도 불필요하게 많은 저널 페이지를 요청하지 않도록,
    # 제목이 최소 한 개의 관심 키워드와 맞는 후보만 보조 조회한다.
    title_text = _normalize_for_matching(title)
    if not abstract and config.include_any and not any(
        _normalize_for_matching(keyword) in title_text for keyword in config.include_any
    ):
        return None

    source = _source(work)
    journal = _string_or_none(source.get("display_name"))
    publishers = _publishers(source)
    doi = _string_or_none(work.get("doi"))
    work_id = str(work.get("id") or doi)
    if _is_excluded(journal, publishers, doi, config):
        return None

    tier = _tier_for(journal, publishers, config)
    if tier == "other" and not config.allow_unlisted_journals:
        return None
    location = work.get("primary_location") if isinstance(work.get("primary_location"), dict) else {}
    landing_page_url = _string_or_none(location.get("landing_page_url")) or doi
    if not abstract:
        abstract = fetch_public_abstract(landing_page_url) or ""
        if abstract:
            print(f"OpenAlex 초록 미제공: 공개 저널 메타데이터로 보완 ({title})", file=sys.stderr)

    text = _normalize_for_matching(f"{title}\n{abstract}")
    any_matches = tuple(keyword for keyword in config.include_any if _normalize_for_matching(keyword) in text)
    all_matches = tuple(keyword for keyword in config.include_all if _normalize_for_matching(keyword) in text)
    if (config.include_any and not any_matches) or len(all_matches) != len(config.include_all):
        return None
    if any(_normalize_for_matching(word) in text for word in config.exclude):
        return None

    matched = tuple(dict.fromkeys((*any_matches, *all_matches)))
    score, keyword_score, tier_score = _score(title, abstract, matched, tier)

    return Paper(
        id=work_id,
        doi=doi,
        title=title,
        abstract=abstract,
        publication_date=_string_or_none(work.get("publication_date")),
        journal=journal,
        publishers=publishers,
        landing_page_url=landing_page_url,
        matched_keywords=matched,
        tier=tier,
        score=score,
        keyword_score=keyword_score,
        tier_score=tier_score,
        summary=_one_sentence_summary(abstract, title, matched),
    )


def _source(work: dict[str, Any]) -> dict[str, Any]:
    location = work.get("primary_location")
    if not isinstance(location, dict):
        return {}
    source = location.get("source")
    return source if isinstance(source, dict) else {}


def _publishers(source: dict[str, Any]) -> tuple[str, ...]:
    names: list[str] = []
    for key in ("host_organization_name", "host_organization_lineage_names"):
        value = source.get(key)
        if isinstance(value, str):
            names.append(value)
        elif isinstance(value, list):
            names.extend(item for item in value if isinstance(item, str))
    return tuple(dict.fromkeys(names))


def _reconstruct_abstract(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, offsets in index.items():
        if isinstance(word, str) and isinstance(offsets, list):
            positions.extend((position, word) for position in offsets if isinstance(position, int))
    return " ".join(word for _, word in sorted(positions))


def _normalize_for_matching(text: str) -> str:
    """출판 메타데이터의 특수 공백·대시를 일반 문자열 검색에 맞춘다."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = re.sub(r"[‐‑‒–—−]", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _one_sentence_summary(abstract: str, fallback: str, matched_keywords: tuple[str, ...]) -> str:
    """초록에서 키워드·결과 표현이 가장 강한 한 문장을 핵심 내용으로 사용한다."""
    cleaned = re.sub(r"\s+", " ", abstract).strip()
    if not cleaned:
        return fallback
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", cleaned) if sentence.strip()]
    result_cues = ("we show", "we demonstrate", "we report", "we find", "we reveal", "we present", "we achieve")

    def sentence_score(sentence: str) -> int:
        normalized = _normalize_for_matching(sentence)
        keyword_hits = sum(_normalize_for_matching(keyword) in normalized for keyword in matched_keywords)
        result_hits = sum(cue in normalized for cue in result_cues)
        return (10 * keyword_hits) + (3 * result_hits)

    summary = max(sentences, key=sentence_score)
    return summary if len(summary) <= 500 else f"{summary[:497].rstrip()}..."


def _is_excluded(
    journal: str | None, publishers: tuple[str, ...], doi: str | None, config: AlertConfig
) -> bool:
    journal_key = (journal or "").casefold()
    if journal_key in {item.casefold() for item in config.excluded_journals}:
        return True
    if (doi or "").casefold().startswith("https://doi.org/10.3390/"):
        return True
    return _has_configured_name(publishers, config.excluded_publishers)


def _tier_for(journal: str | None, publishers: tuple[str, ...], config: AlertConfig) -> str:
    journal_key = (journal or "").casefold()
    for tier in ("tier_1", "tier_2", "tier_3", "tier_4"):
        if journal_key in {item.casefold() for item in config.journal_tiers[tier]}:
            return tier
    return "other"


def _has_configured_name(candidates: tuple[str, ...], configured_names: tuple[str, ...]) -> bool:
    """MDPI AG처럼 설정값을 포함하는 출판사 표기도 일치로 본다."""
    return any(
        configured.casefold() in candidate.casefold()
        for candidate in candidates
        for configured in configured_names
    )


def _score(title: str, abstract: str, matched_keywords: tuple[str, ...], tier: str) -> tuple[int, int, int]:
    """키워드 관련도와 저널 tier를 함께 반영한다.

    키워드별 가중치와 Tier 1~4 가점을 명시적으로 합산한다.
    """
    tier_score = {"tier_1": 120, "tier_2": 90, "tier_3": 60, "tier_4": 30, "other": 0}[tier]
    keyword_score = sum(_keyword_weight(keyword) for keyword in matched_keywords)
    return keyword_score + tier_score, keyword_score, tier_score


def _keyword_weight(keyword: str) -> int:
    normalized = _normalize_for_matching(keyword)
    if "spin" in normalized or "magnon" in normalized:
        return 20
    if normalized in {_normalize_for_matching(item) for item in LOW_PRIORITY_KEYWORDS}:
        return 10
    return 30


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def write_results(papers: list[Paper], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(paper) for paper in papers], ensure_ascii=False, indent=2), encoding="utf-8"
    )


def print_results(papers: list[Paper]) -> None:
    if not papers:
        print("조건에 맞는 신규 논문이 없습니다.")
        return
    print(f"추천 후보 {len(papers)}편")
    for number, paper in enumerate(papers, start=1):
        print(f"\n{number}. [{paper.tier}] {paper.title}")
        print(
            f"   {paper.journal or '저널 정보 없음'} | {paper.publication_date or '날짜 정보 없음'}"
            f" | 점수 {paper.score} (키워드 {paper.keyword_score} + Tier {paper.tier_score})"
        )
        print(f"   일치: {', '.join(paper.matched_keywords)}")
        print(f"   핵심: {paper.summary_ko or paper.summary}")
        print(f"   {paper.landing_page_url or paper.doi or paper.id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAlex 기반 Research Alert 후보 수집")
    parser.add_argument("--config", type=Path, default=Path("config/keywords.yaml"))
    parser.add_argument("--output", type=Path, default=Path("data/latest_candidates.json"))
    parser.add_argument("--per-keyword", type=int, default=100, help="키워드당 OpenAlex 최대 검색 결과")
    parser.add_argument("--max-pages", type=int, default=3, help="키워드당 최대 페이지 수")
    args = parser.parse_args()
    if args.per_keyword < 1 or args.per_keyword > 100:
        parser.error("--per-keyword는 1~100 사이의 정수여야 합니다.")
    if args.max_pages < 1 or args.max_pages > 10:
        parser.error("--max-pages는 1~10 사이의 정수여야 합니다.")

    try:
        config = load_config(args.config)
        api_key = os.getenv("OPENALEX_API_KEY")
        if not api_key:
            raise RuntimeError("OPENALEX_API_KEY 환경 변수가 필요합니다. OpenAlex 무료 API 키를 설정하세요.")
        papers = collect(config, args.per_keyword, args.max_pages, api_key)
        write_results(papers, args.output)
    except ValueError as error:
        print(f"설정 오류: {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        print(f"수집 오류: {error}", file=sys.stderr)
        return 2

    print_results(papers)
    print(f"\n상세 결과 저장: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
