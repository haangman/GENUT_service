"""SQLAlchemy ORM 모델.

설계 메모:
- enum 값은 String으로 저장(SQLite/Postgres 공통, 이식성 우선).
- 경로 필드는 서비스 계층에서 `/`로 정규화하여 저장한다.
- product_locks.product_id를 PK로 두어 "한 프로덕트당 락 1개"를 DB 차원에서 보장한다.
- genut_instances.current_job_id는 순환 FK를 피하기 위해 soft 참조(일반 int)로 둔다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from genut_service.db.base import Base
from genut_service.enums import (
    JobKind,
    JobOrigin,
    JobStatus,
    LlmModel,
    TestGenerationMode,
    WorkerStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """created_at/updated_at 공통 컬럼."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Product(TimestampMixin, Base):
    """테스트 생성 대상 프로덕트. 경로/명령은 프로덕트 루트 기준 상대값으로 저장."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 이름은 중복 허용(서로 다른 id·정보로 등록). 같은 이름끼리는 스케줄러가 병렬 실행을 막는다.
    name: Mapped[str] = mapped_column(String(255))
    product_code: Mapped[str] = mapped_column(String(255))
    git_url: Mapped[str] = mapped_column(String(1024))
    git_ref: Mapped[str] = mapped_column(String(255), default="main")

    compile_db_rel: Mapped[str] = mapped_column(String(1024))
    out_tests_rel: Mapped[str] = mapped_column(String(1024))
    # 영속 코드 체크아웃 경로(선택). 지정 시 매 작업마다 fresh clone 대신 제자리 업데이트.
    code_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cmake_configure_cmd: Mapped[str] = mapped_column(Text)
    cmake_build_cmd: Mapped[str] = mapped_column(Text)
    test_run_cmd: Mapped[str] = mapped_column(Text)

    test_generation_mode: Mapped[str] = mapped_column(
        String(16), default=TestGenerationMode.CPP.value
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 테스트 대상 파일 수집 시 path 기준으로 제외할 글롭 패턴(예: "*test*"). 기본 빈 목록.
    exclude_globs: Mapped[list[str]] = mapped_column(JSON, default=list)

    # 자동 실행(주기적 테스트 생성) 프로덕트 관련. 비자동 프로덕트는 모두 기본값.
    auto_run: Mapped[bool] = mapped_column(Boolean, default=False)
    # 자동 수행 주기(초). None=비자동. (실제 주기 실행은 추후 스케줄러에서 구현)
    auto_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 자동 생성 대상으로 확정된 파일 목록(프로덕트 루트 기준 상대경로). 향후 잡 file_list 근거.
    auto_file_list: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 파일별 하위 CMakeLists.txt 양식(placeholder `filename`을 파일 stem으로 치환). 비자동은 None.
    cmake_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 마지막 auto 사이클을 큐잉한 시각(주기 도래 판정 기준). None=미실행.
    last_auto_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 마지막 변경 감지(diff)의 기준 커밋(HEAD 해시). None=최초 실행 전.
    last_scanned_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)

    patches: Mapped[list["Patch"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="Patch.order_index",
    )
    jobs: Mapped[list["Job"]] = relationship(back_populates="product")


class Patch(TimestampMixin, Base):
    """프로덕트 클론 후 순서대로 적용할 patch(unified diff 텍스트)."""

    __tablename__ = "patches"
    __table_args__ = (UniqueConstraint("product_id", "order_index", name="uq_patch_order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)

    product: Mapped["Product"] = relationship(back_populates="patches")


class GenutInstance(TimestampMixin, Base):
    """등록된 GENUT 인스턴스 = 워커 1개. credential은 응답에서 제외한다."""

    __tablename__ = "genut_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    repo_url: Mapped[str] = mapped_column(String(1024))
    repo_ref: Mapped[str] = mapped_column(String(255), default="main")
    # ASSURE repo URL(선택). 지정 시 GENUT 코드와 같은 depth(형제 디렉터리)에 받아둔다.
    assure_repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    ds_assist_credential_key: Mapped[str] = mapped_column(String(1024))
    ds_assist_send_system_name: Mapped[str] = mapped_column(String(255))
    # DS_ASSIST_USER_ID(.env). 기존 행 호환을 위해 nullable.
    ds_assist_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    max_attempts: Mapped[int] = mapped_column(Integer, default=10)
    run_command: Mapped[str] = mapped_column(String(1024), default="python -m genut")
    # GENUT가 사용할 LLM 모델 — .env에 LLM_MODEL=<값>으로 전달된다
    llm_model: Mapped[str] = mapped_column(String(32), default=LlmModel.GPT_OSS.value)
    # 영속 코드 체크아웃 경로(선택). 지정 시 매 작업마다 fresh clone 대신 제자리 업데이트.
    code_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    worker_status: Mapped[str] = mapped_column(
        String(16), default=WorkerStatus.IDLE.value
    )
    # 순환 FK 회피용 soft 참조
    current_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Job(TimestampMixin, Base):
    """테스트 생성 요청 1건."""

    __tablename__ = "jobs"
    # 핫패스 인덱스: 스케줄러 1초 틱의 claim(status,kind)·배타 조회(product_id,status),
    # 이력 폴링의 origin 필터. SQLite는 FK에 자동 인덱스를 만들지 않는다.
    __table_args__ = (
        Index("ix_jobs_status_kind", "status", "kind"),
        Index("ix_jobs_product_status", "product_id", "status"),
        Index("ix_jobs_origin", "origin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    genut_instance_id: Mapped[int | None] = mapped_column(
        ForeignKey("genut_instances.id"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED.value)
    # 실행 경로 구분: genut(워커 실행) | auto_scan/auto_diff(스케줄러 auto 단계가 실행)
    kind: Mapped[str] = mapped_column(String(16), default=JobKind.GENUT.value)
    # 생성 주체 구분: manual(수동 제출) | auto(auto 모드 주기 실행)
    origin: Mapped[str] = mapped_column(String(16), default=JobOrigin.MANUAL.value)
    function_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # compile-check를 통과해 실제 제출되는 파일들(프로덕트 루트 기준 상대경로)
    file_list: Mapped[list[str]] = mapped_column(JSON, default=list)
    # compile_commands.json에 없어 제외된 파일들(정보용)
    excluded_files: Mapped[list[str]] = mapped_column(JSON, default=list)

    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=0)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="jobs")
    genut_instance: Mapped["GenutInstance | None"] = relationship()
    events: Mapped[list["JobEvent"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobEvent.id",
    )

    @property
    def genut_name(self) -> str | None:
        """배정된 GENUT 인스턴스 이름(미배정/삭제면 None) — 이력 표시용."""
        return self.genut_instance.name if self.genut_instance is not None else None

    @property
    def product_name(self) -> str | None:
        """대상 프로덕트 이름 — 이력 표시용(id만으로는 알아보기 어렵다)."""
        return self.product.name if self.product is not None else None


class JobEvent(Base):
    """job 타임라인/로그(append-only). 대용량 stdout/stderr를 message에 담는다."""

    __tablename__ = "job_events"
    # 로그 증분 폴링(WHERE job_id=? AND id>?)이 1.5초마다 도는 핫패스 — 복합 인덱스 필수
    __table_args__ = (Index("ix_job_events_job_id_id", "job_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    level: Mapped[str] = mapped_column(String(16), default="info")
    phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped["Job"] = relationship(back_populates="events")


class ProductLock(Base):
    """동일 프로덕트 배타 락. product_id PK가 "프로덕트당 락 1개"를 보장한다."""

    __tablename__ = "product_locks"

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    genut_instance_id: Mapped[int] = mapped_column(ForeignKey("genut_instances.id"))
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


class TestStatusSnapshot(Base):
    """이름별 테스트 현황 스냅샷(백그라운드 리프레셔가 갱신, API는 읽기만).

    실시간 풀스캔 대신 이 스냅샷을 읽어 테스트 현황 페이지가 즉시 응답한다.
    쓰기는 메인 프로세스(스케줄러 리프레셔)만 수행하고, 독립 상태 서버는 읽기 전용으로
    공유한다(SQLite WAL). fingerprint는 이름 그룹의 (id, updated_at) 직렬화 — 프로덕트
    등록/수정 시 스냅샷이 오래됐음을 판별하는 용도다.
    """

    __tablename__ = "test_status_snapshots"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(2048))
    summary: Mapped[dict] = mapped_column(JSON)  # NameTestSummary dict
    detail: Mapped[list] = mapped_column(JSON)  # TargetFileStatus dict 리스트
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
