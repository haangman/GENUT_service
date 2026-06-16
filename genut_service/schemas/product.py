"""프로덕트 관련 Pydantic 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from genut_service.enums import TestGenerationMode
from genut_service.paths import normalize_code_path, normalize_rel_path


def _norm_code_path(value: str | None) -> str | None:
    """빈/공백은 None, 그 외는 정규화(절대/상대 허용)."""
    if value is None:
        return None
    normalized = normalize_code_path(value)
    return normalized or None


class PatchIn(BaseModel):
    """입력 patch."""

    name: str
    content: str
    order_index: int = 0


class PatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    content: str
    order_index: int


class ProductBase(BaseModel):
    name: str
    product_code: str
    git_url: str
    git_ref: str = "main"
    compile_db_rel: str
    out_tests_rel: str
    cmake_configure_cmd: str
    cmake_build_cmd: str
    test_run_cmd: str
    test_generation_mode: TestGenerationMode = TestGenerationMode.CPP
    active: bool = True
    code_path: str | None = None

    @field_validator("compile_db_rel", "out_tests_rel")
    @classmethod
    def _normalize_paths(cls, value: str) -> str:
        return normalize_rel_path(value)

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)


class ProductCreate(ProductBase):
    patches: list[PatchIn] = []


class ProductUpdate(BaseModel):
    """부분 수정. 제공된 필드만 갱신한다. patches가 주어지면 전체 교체."""

    name: str | None = None
    product_code: str | None = None
    git_url: str | None = None
    git_ref: str | None = None
    compile_db_rel: str | None = None
    out_tests_rel: str | None = None
    cmake_configure_cmd: str | None = None
    cmake_build_cmd: str | None = None
    test_run_cmd: str | None = None
    test_generation_mode: TestGenerationMode | None = None
    active: bool | None = None
    code_path: str | None = None
    patches: list[PatchIn] | None = None

    @field_validator("compile_db_rel", "out_tests_rel")
    @classmethod
    def _normalize_paths(cls, value: str | None) -> str | None:
        return None if value is None else normalize_rel_path(value)

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patches: list[PatchRead] = []
