"""GENUT 인스턴스(=워커) 스키마. credential key는 응답에 포함하지 않는다."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GenutBase(BaseModel):
    name: str
    repo_url: str
    repo_ref: str = "main"
    ds_assist_send_system_name: str
    max_attempts: int = Field(default=10, ge=1)
    run_command: str = "python -m genut"
    enabled: bool = True


class GenutCreate(GenutBase):
    ds_assist_credential_key: str


class GenutUpdate(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    repo_ref: str | None = None
    ds_assist_send_system_name: str | None = None
    # 미지정/None이면 기존 값을 유지(write-only)
    ds_assist_credential_key: str | None = None
    max_attempts: int | None = Field(default=None, ge=1)
    run_command: str | None = None
    enabled: bool | None = None


class GenutRead(GenutBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    worker_status: str
    current_job_id: int | None
