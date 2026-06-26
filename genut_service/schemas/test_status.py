"""프로덕트별 테스트 현황 스키마."""

from __future__ import annotations

from pydantic import BaseModel


class TestFileInfo(BaseModel):
    """매칭된 테스트 파일 1건."""

    name: str
    path: str


class TargetFileStatus(BaseModel):
    """테스트 생성 대상 파일 1건과 그에 매칭된 테스트 파일들."""

    name: str
    path: str
    test_count: int
    test_files: list[TestFileInfo]
