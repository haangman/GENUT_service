"""GENUT 인스턴스(=워커) 스키마. credential key는 응답에 포함하지 않는다."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from genut_service.paths import normalize_code_path

# GENUT가 사용할 LLM 모델 선택지 (.env의 LLM_MODEL 값)
LlmModelName = Literal["gptOss", "SSCR_SE"]


def _norm_code_path(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_code_path(value)
    return normalized or None


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class GenutBase(BaseModel):
    name: str
    repo_url: str
    repo_ref: str = "main"
    assure_repo_url: str | None = None
    ds_assist_send_system_name: str
    ds_assist_user_id: str | None = None
    max_attempts: int = Field(default=10, ge=1)
    run_command: str = "python -m genut"
    llm_model: LlmModelName = "gptOss"
    enabled: bool = True
    code_path: str | None = None

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)

    @field_validator("ds_assist_user_id", "assure_repo_url")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_to_none(value)


class GenutCreate(GenutBase):
    ds_assist_credential_key: str


class GenutUpdate(BaseModel):
    name: str | None = None
    repo_url: str | None = None
    repo_ref: str | None = None
    assure_repo_url: str | None = None
    ds_assist_send_system_name: str | None = None
    ds_assist_user_id: str | None = None
    # 미지정/None이면 기존 값을 유지(write-only)
    ds_assist_credential_key: str | None = None
    max_attempts: int | None = Field(default=None, ge=1)
    run_command: str | None = None
    llm_model: LlmModelName | None = None
    enabled: bool | None = None
    code_path: str | None = None

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)

    @field_validator("ds_assist_user_id", "assure_repo_url")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        return _empty_to_none(value)


class GenutRead(GenutBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    worker_status: str
    current_job_id: int | None
