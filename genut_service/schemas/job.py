"""Job 관련 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genut_service.schemas.common import UtcDatetime


class JobCreate(BaseModel):
    product_id: int
    files: list[str]
    function_name: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    genut_instance_id: int | None
    # 배정된 GENUT 인스턴스 이름(미배정이면 None) — 이력 화면에서 어떤 GENUT이
    # 실행했는지 표시하는 용도
    genut_name: str | None = None
    status: str
    kind: str
    origin: str
    function_name: str | None
    file_list: list[str]
    excluded_files: list[str]
    attempt: int
    submitted_at: UtcDatetime
    started_at: UtcDatetime | None
    finished_at: UtcDatetime | None
    result_summary: str | None
    error: str | None


class AutoHistoryGroup(BaseModel):
    """auto 전용 이력 페이지의 프로덕트별 그룹(최근 N개 + 전체 수)."""

    product_id: int
    product_name: str
    product_code: str
    auto_interval_seconds: int | None
    total: int
    jobs: list[JobRead]


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    ts: UtcDatetime
    level: str
    phase: str | None
    message: str
    payload: dict | None
