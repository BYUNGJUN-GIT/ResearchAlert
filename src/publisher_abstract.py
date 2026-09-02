"""OpenAlex에 초록이 없는 논문의 공개 랜딩 페이지 메타데이터를 읽는다."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

USER_AGENT = "ResearchAlert/0.1 (personal academic literature alert)"
MAX_HTML_BYTES = 2_000_000
_ABSTRACT_META_NAMES = {"citation_abstract", "dc.description", "description", "og:description"}


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = {key.casefold(): value for key, value in attrs if value is not None}
        name = str(values.get("name") or values.get("property") or "").casefold()
        content = str(values.get("content") or "").strip()
        if not content or name not in _ABSTRACT_META_NAMES:
            return
        priority = 0 if name == "citation_abstract" else 1 if name == "dc.description" else 2
        self.candidates.append((priority, content))


def fetch_public_abstract(url: str | None) -> str | None:
    """DOI 또는 저널 랜딩 페이지의 공개 초록 메타데이터만 반환한다.

    전문 PDF·로그인 페이지는 읽지 않고, DOI 리디렉션 후 HTML의 표준 인용 메타데이터만 확인한다.
    """
    if not url or urlparse(url).scheme not in {"http", "https"}:
        return None
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                return None
            raw = response.read(MAX_HTML_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
    except (HTTPError, URLError, OSError, ValueError):
        return None

    parser = _MetadataParser()
    try:
        parser.feed(raw.decode(charset, errors="replace"))
        parser.close()
    except (ValueError, UnicodeError):
        return None
    if not parser.candidates:
        return None
    _, value = min(parser.candidates, key=lambda candidate: candidate[0])
    cleaned = re.sub(r"\s+", " ", html.unescape(value)).strip()
    return cleaned or None
