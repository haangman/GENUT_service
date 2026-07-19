"""프로덕트 관련 Pydantic 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator

from genut_service.enums import GitUpdateMode, Project, TestGenerationMode
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
    # 영속 체크아웃 갱신 방식: reset(원격 강제 일치) | rebase(로컬 커밋 유지)
    git_update_mode: GitUpdateMode = GitUpdateMode.RESET
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
    git_update_mode: GitUpdateMode | None = None
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


class PullCodeRequest(BaseModel):
    """코드 저장 경로로 git 코드를 받아오는(다운로드) 요청.

    폼 값 기반(id 불필요)이라 저장 전 신규 등록 중에도 동작한다.
    """

    git_url: str
    git_ref: str = "main"
    code_path: str
    # 제자리 갱신 방식(폼 값 — runner와 동일하게 rebase면 로컬 커밋 유지)
    git_update_mode: GitUpdateMode = GitUpdateMode.RESET
    # 지정 시 제자리 업데이트(reset)에서 생성 테스트 폴더를 보존한다(runner와 동일 보호)
    out_tests_rel: str | None = None
    # 지정 시 체크아웃 직후 order_index 순서대로 적용한다(runner와 동일한 멱등 적용)
    patches: list[PatchIn] = []

    @field_validator("git_url")
    @classmethod
    def _require_git_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Git URL이 비어 있다")
        return value.strip()

    @field_validator("code_path")
    @classmethod
    def _require_code_path(cls, value: str) -> str:
        normalized = _norm_code_path(value)
        if normalized is None:
            raise ValueError("코드 저장 경로가 비어 있다")
        return normalized

    @field_validator("out_tests_rel")
    @classmethod
    def _normalize_out_tests(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return normalize_rel_path(value)


class PullCodeResponse(BaseModel):
    """다운로드 결과. path는 실제 받은(해석된) 경로, log는 폼 로그창용 부가 정보."""

    path: str
    detail: str
    log: str = ""


class FetchGerritPatchRequest(BaseModel):
    """Gerrit change 주소/번호로 diff를 가져오는 요청 — 폼 값 기반(저장 전에도 동작).

    diff는 git_url로 change ref를 fetch해 얻는다(code_path 체크아웃 필요).
    """

    git_url: str
    code_path: str
    change: str

    @field_validator("git_url")
    @classmethod
    def _require_git_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Git URL이 비어 있다")
        return value.strip()

    @field_validator("code_path")
    @classmethod
    def _require_code_path(cls, value: str) -> str:
        normalized = _norm_code_path(value)
        if normalized is None:
            raise ValueError("코드 저장 경로가 비어 있다")
        return normalized

    @field_validator("change")
    @classmethod
    def _require_change(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Gerrit change 주소가 비어 있다")
        return value.strip()


class FetchGerritPatchResponse(BaseModel):
    """가져온 패치. name/content는 폼 패치 행에 그대로 들어간다."""

    name: str
    content: str
    ref: str
    subject: str = ""


class RunCommandRequest(BaseModel):
    """폼 단계 명령 시험 실행 요청 — code_path를 작업 디렉터리로 command를 실행한다."""

    command: str
    code_path: str

    @field_validator("command")
    @classmethod
    def _require_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("실행할 명령이 비어 있다")
        return value.strip()

    @field_validator("code_path")
    @classmethod
    def _require_code_path(cls, value: str) -> str:
        normalized = _norm_code_path(value)
        if normalized is None:
            raise ValueError("코드 저장 경로가 비어 있다")
        return normalized


class RunCommandResponse(BaseModel):
    """명령 실행 결과. 명령 자체의 실패(비0 exit)는 HTTP 오류가 아니라 결과로 전달한다."""

    exit_code: int
    output: str
    duration_seconds: float


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
