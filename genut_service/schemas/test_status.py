"""프로덕트별 테스트 현황 스키마. 동명 프로덕트는 이름 1개로 합산(합집합)한다."""

from __future__ import annotations

from pydantic import BaseModel


class TestFileInfo(BaseModel):
    """매칭된 테스트 파일 1건. product_codes는 이 파일이 속한 프로덕트 id들."""

    name: str
    path: str
    product_codes: list[str]
    log_path: str | None = None


class TargetFileStatus(BaseModel):
    """테스트 생성 대상 파일 1건과 그에 매칭된 테스트 파일들(동명 변이 합산).

    test_files는 생성 성공, failed_test_files는 생성했으나 최종 실패한 테스트 파일이다.
    """

    name: str
    path: str
    product_codes: list[str]
    test_count: int
    test_files: list[TestFileInfo]
    fail_count: int
    failed_test_files: list[TestFileInfo]


class NameTestSummary(BaseModel):
    """이름으로 묶은 프로덕트의 테스트 현황 요약(목록 페이지용)."""

    name: str
    product_codes: list[str]
    test_generation_mode: str
    target_file_count: int
    total_test_count: int
    total_fail_count: int


class FileContent(BaseModel):
    """테스트 코드/로그 파일 1건의 내용(뷰어용). path는 프로덕트 root 기준 상대경로."""

    path: str
    content: str
