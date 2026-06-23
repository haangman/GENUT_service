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
