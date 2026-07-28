"""공용 스키마."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, PlainSerializer

T = TypeVar("T")


def _ensure_utc_iso(value: datetime) -> str:
    """datetime을 타임존 인식 ISO 문자열로 직렬화한다.

    DB(SQLite 등)에서 돌아온 naive datetime은 UTC로 간주한다. 표식이 없으면
    클라이언트의 `new Date(...)`가 로컬 시각으로 오해해 실행 중 job의 경과 시간이
    타임존 오프셋만큼 어긋나므로, 항상 오프셋(`+00:00`)을 붙여 내보낸다.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# API로 내보내는 datetime 필드용. naive면 UTC로 간주하고 tz 인식 ISO로 직렬화한다.
UtcDatetime = Annotated[
    datetime, PlainSerializer(_ensure_utc_iso, return_type=str, when_used="json")
]


class Page(BaseModel, Generic[T]):
    """페이지네이션 응답 봉투."""

    items: list[T]
    total: int
    page: int
    page_size: int


# ref 입력에서 자동 제거하는 흔한 접두(우선순위 순 — 가장 구체적인 것 먼저, 1회만 제거).
_REF_PREFIXES = ("refs/remotes/origin/", "refs/heads/", "origin/")


def normalize_git_ref(value: str) -> str:
    """git ref 입력 정규화: 공백 제거 + 흔한 접두(`origin/`·`refs/heads/` 등) 제거.

    서비스는 ref를 `origin/<ref>`로 해석하므로 순수 브랜치/태그명이어야 한다.
    사용자가 `origin/feature`처럼 입력하는 흔한 실수를 저장 시점에 흡수한다.
    접두만 있고 이름이 비면 ValueError(422로 표면화 — 조용한 오저장 방지).
    """
    ref = (value or "").strip()
    if not ref:
        return ref  # 빈 입력은 기존 의미(기본값/업스트림 추적) 유지
    for prefix in _REF_PREFIXES:
        if ref.startswith(prefix):
            ref = ref[len(prefix):]
            break
    if not ref:
        raise ValueError("올바른 브랜치/태그명이 아니다 — 접두 뒤에 이름이 없다")
    return ref
