"""공용 스키마."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """페이지네이션 응답 봉투."""

    items: list[T]
    total: int
    page: int
    page_size: int
