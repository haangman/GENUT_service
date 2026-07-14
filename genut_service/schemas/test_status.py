"""프로덕트별 테스트 현황 스키마. 동명 프로덕트는 이름 1개로 합산(합집합)한다."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TestFileInfo(BaseModel):
    """매칭된 테스트 파일 1건. product_codes는 이 파일이 속한 프로덕트 id들.

    case_count는 파일 안의 테스트 케이스 수(성공 파일만; 실패 파일은 None).
    """

    name: str
    path: str
    product_codes: list[str]
    log_path: str | None = None
    case_count: int | None = None


class TargetFileStatus(BaseModel):
    """테스트 생성 대상 파일 1건과 그에 매칭된 테스트 파일들(동명 변이 합산).

    test_files는 생성 성공, failed_test_files는 생성했으나 최종 실패한 테스트 파일이다.
    """

    name: str
    path: str
    product_codes: list[str]
    test_count: int
    test_files: list[TestFileInfo]
    case_count: int
    fail_count: int
    failed_test_files: list[TestFileInfo]


class NameTestSummary(BaseModel):
    """(프로젝트, 이름)으로 묶은 프로덕트의 테스트 현황 요약(목록 페이지용).

    generated_at: 스냅샷 생성 시각(스냅샷에서 응답한 경우). 실시간 폴백 스캔이면 None.
    """

    project: str
    name: str
    product_codes: list[str]
    test_generation_mode: str
    target_file_count: int
    total_test_count: int
    total_case_count: int
    total_fail_count: int
    generated_at: datetime | None = None


class FileContent(BaseModel):
    """테스트 코드/로그 파일 1건의 내용(뷰어용). path는 프로덕트 root 기준 상대경로."""

    path: str
    content: str
