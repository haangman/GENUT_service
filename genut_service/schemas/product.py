"""프로덕트 관련 Pydantic 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from genut_service.enums import Project, TestGenerationMode
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
    project: Project = Project.ULYSSES
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
    exclude_globs: list[str] = []

    # 자동 실행(주기적 테스트 생성) 프로덕트 관련. 비자동은 모두 기본값.
    auto_run: bool = False
    auto_interval_seconds: int | None = None
    auto_file_list: list[str] = []
    cmake_template: str | None = None

    @field_validator("compile_db_rel", "out_tests_rel")
    @classmethod
    def _normalize_paths(cls, value: str) -> str:
        return normalize_rel_path(value)

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)

    @field_validator("exclude_globs")
    @classmethod
    def _clean_globs(cls, value: list[str]) -> list[str]:
        return [g.strip() for g in value if g and g.strip()]


class ProductCreate(ProductBase):
    patches: list[PatchIn] = []


class ProductUpdate(BaseModel):
    """부분 수정. 제공된 필드만 갱신한다. patches가 주어지면 전체 교체."""

    project: Project | None = None
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
    exclude_globs: list[str] | None = None
    auto_run: bool | None = None
    auto_interval_seconds: int | None = None
    auto_file_list: list[str] | None = None
    cmake_template: str | None = None
    patches: list[PatchIn] | None = None

    @field_validator("compile_db_rel", "out_tests_rel")
    @classmethod
    def _normalize_paths(cls, value: str | None) -> str | None:
        return None if value is None else normalize_rel_path(value)

    @field_validator("code_path")
    @classmethod
    def _normalize_code_path(cls, value: str | None) -> str | None:
        return _norm_code_path(value)

    @field_validator("exclude_globs")
    @classmethod
    def _clean_globs(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else [g.strip() for g in value if g and g.strip()]


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patches: list[PatchRead] = []


class TargetFilesRequest(BaseModel):
    """폼 단계 대상 파일 미리보기 요청(아직 프로덕트 없음). code_path는 로컬 경로."""

    code_path: str
    compile_db_rel: str
    exclude_globs: list[str] = []


class TargetFileItem(BaseModel):
    """미리보기 대상 파일 1건. excluded_by_pattern은 제외 글롭에 걸렸는지."""

    path: str
    excluded_by_pattern: bool


class TargetFilesResponse(BaseModel):
    files: list[TargetFileItem]
