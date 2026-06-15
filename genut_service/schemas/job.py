"""Job 관련 스키마."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobCreate(BaseModel):
    product_id: int
    files: list[str]
    function_name: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    genut_instance_id: int | None
    status: str
    function_name: str | None
    file_list: list[str]
    excluded_files: list[str]
    attempt: int
    submitted_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result_summary: str | None
    error: str | None


class JobEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    ts: datetime
    level: str
    phase: str | None
    message: str
    payload: dict | None
