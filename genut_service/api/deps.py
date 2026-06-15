"""API 공용 의존성."""

from __future__ import annotations

from fastapi import Query

from genut_service.db.base import get_session  # noqa: F401  (라우터에서 재사용)


class PageParams:
    """목록 페이지네이션 쿼리 파라미터."""

    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=200),
    ) -> None:
        self.page = page
        self.page_size = page_size
