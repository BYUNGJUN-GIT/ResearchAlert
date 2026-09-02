"""Nature 공식 RSS에서 OpenAlex 색인 전의 최신 논문을 읽는다."""

from __future__ import annotations

import html
import re
import sys
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.request import Request, urlopen
from xml.etree import ElementTree

USER_AGENT = "ResearchAlert/0.1 (personal academic literature alert)"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
NATURE_ARTICLE_ID_PATTERN = re.compile(r"/articles/(s\d+-\d+-\d+-\d+)", re.IGNORECASE)
TAG_PATTERN = re.compile(r"<[^>]+>")


def fetch_rss_works(feeds: Iterable[Any], from_date: str) -> list[dict[str, Any]]:
    """설정된 RSS에서 기준일 이후의 항목을 OpenAlex 호환 구조로 반환한다.

    개별 피드 오류는 전체 일일 알림을 중단시키지 않는다. OpenAlex 결과는 계속 사용된다.
    """
    works: list[dict[str, Any]] = []
    for feed in feeds:
        try:
            works.extend(_fetch_one_feed(feed.journal, feed.url, from_date))
        except (OSError, ElementTree.ParseError, ValueError) as error:
            print(f"Nature RSS 건너뜀 ({feed.journal}): {error}", file=sys.stderr)
    return works


def _fetch_one_feed(journal: str, url: str, from_date: str) -> list[dict[str, Any]]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        root = ElementTree.parse(response).getroot()

    works: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        description = _clean_html(_child_text(item, "description"))
        published = _rss_date(_child_text(item, "pubDate"))
        if not title or not link or not published or published < from_date:
            continue
        doi_match = DOI_PATTERN.search(f"{link} {description}")
        doi = f"https://doi.org/{doi_match.group(0)}" if doi_match else _nature_doi_from_link(link)
        works.append(
            {
                "id": doi or link,
                "doi": doi,
                "title": title,
                "abstract_inverted_index": _to_inverted_index(description),
                "publication_date": published,
                "primary_location": {
                    "landing_page_url": link,
                    "source": {"display_name": journal, "host_organization_name": "Nature Portfolio"},
                },
            }
        )
    return works


def _child_text(element: ElementTree.Element, name: str) -> str:
    child = element.find(name)
    return child.text.strip() if child is not None and child.text else ""


def _rss_date(value: str) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC).date().isoformat()
    except (TypeError, ValueError):
        return None


def _clean_html(value: str) -> str:
    return html.unescape(TAG_PATTERN.sub(" ", value)).strip()


def _nature_doi_from_link(link: str) -> str | None:
    """Nature article URL의 s 접두어 식별자는 DOI의 뒷부분과 동일하다."""
    match = NATURE_ARTICLE_ID_PATTERN.search(link)
    return f"https://doi.org/10.1038/{match.group(1)}" if match else None


def _to_inverted_index(text: str) -> dict[str, list[int]]:
    inverted: dict[str, list[int]] = {}
    for position, word in enumerate(text.split()):
        inverted.setdefault(word, []).append(position)
    return inverted
