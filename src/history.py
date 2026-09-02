"""발송 완료 논문의 DOI/OpenAlex ID 이력을 관리한다."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


def load_sent_ids(path: Path, retention_days: int = 365) -> set[str]:
    """보존 기간 안에 발송된 논문의 식별자를 반환한다."""
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"발송 이력 파일을 읽을 수 없습니다: {path}") from exc
    papers = payload.get("papers") if isinstance(payload, dict) else None
    if not isinstance(papers, list):
        raise ValueError("발송 이력의 papers 항목은 목록이어야 합니다.")

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    sent_ids: set[str] = set()
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        identifier = paper.get("id")
        sent_at = paper.get("sent_at")
        if not isinstance(identifier, str) or not isinstance(sent_at, str):
            continue
        try:
            if datetime.fromisoformat(sent_at.replace("Z", "+00:00")) >= cutoff:
                sent_ids.add(identifier.casefold())
        except ValueError:
            continue
    return sent_ids


def record_delivered(path: Path, papers: Iterable[Any], retention_days: int = 365) -> None:
    """성공적으로 전달된 논문만 저장한다. 발송 실패 시 이 함수를 호출하지 않는다."""
    existing = _load_entries(path)
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    for paper in papers:
        identifier = getattr(paper, "doi", None) or getattr(paper, "id", None)
        if isinstance(identifier, str) and identifier:
            existing[identifier.casefold()] = {"id": identifier, "sent_at": now}

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    kept = [
        entry
        for entry in existing.values()
        if datetime.fromisoformat(entry["sent_at"].replace("Z", "+00:00")) >= cutoff
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": 1, "papers": sorted(kept, key=lambda item: item["sent_at"])}, indent=2),
        encoding="utf-8",
    )


def _load_entries(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"발송 이력 파일을 읽을 수 없습니다: {path}") from exc
    papers = payload.get("papers") if isinstance(payload, dict) else None
    if not isinstance(papers, list):
        raise ValueError("발송 이력의 papers 항목은 목록이어야 합니다.")
    return {
        entry["id"].casefold(): entry
        for entry in papers
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and isinstance(entry.get("sent_at"), str)
    }
