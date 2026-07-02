"""auto 모드 주기 실행: 사이클 큐잉·준비(prep) job 디스패치/실행.

스케줄러 루프가 매 tick 호출한다(단일 writer 전제 — engine.claim_jobs와 동일).

- enqueue_due_cycles: 주기가 도래한 auto 프로덕트마다 준비 job 쌍(auto_diff →
  auto_scan, id 오름차순)을 큐잉하고 last_auto_run_at을 갱신한다.
- claim_prep_jobs: queued 준비 job을 프로덕트 "이름"당 1개씩 running으로 전이한다.
  GENUT job이 실행 중(product_locks)이거나 이미 running 준비 job이 있는 이름은
  스킵(=다음 tick으로 연기)한다 → git reset 충돌 방지 + diff→scan 순서 보장.
- process_prep_job: running 준비 job 1건을 실행한다(스레드에서 호출).
  종료는 전용 _finish_prep으로 처리한다 — 준비 job은 락·워커를 쓰지 않으므로
  engine.finish_job(락 해제·워커 idle)과 접점을 만들지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Job, JobEvent, Product, ProductLock
from genut_service.enums import (
    PREP_KINDS,
    TERMINAL_STATUSES,
    JobKind,
    JobOrigin,
    JobPhase,
    JobStatus,
)
from genut_service.runner import process_registry
from genut_service.services import auto_run_service

_PREP_KIND_VALUES = tuple(kind.value for kind in PREP_KINDS)
_TERMINAL_VALUES = tuple(status.value for status in TERMINAL_STATUSES)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_due_cycles(session: Session, now: datetime | None = None) -> list[int]:
    """주기 도래한 auto 프로덕트마다 준비 job 쌍을 큐잉한다. 생성된 job id 목록 반환.

    이전 사이클의 준비 job이 아직 종료되지 않았으면(대기/실행 중) 이번 주기는
    건너뛴다(사이클 중복 방지 — 밀린 사이클은 다음 주기에 자연 재개된다).
    """
    now = now or _utcnow()
    created: list[int] = []
    products = session.scalars(
        select(Product).where(
            Product.auto_run.is_(True),
            Product.active.is_(True),
            Product.auto_interval_seconds.is_not(None),
            Product.auto_interval_seconds > 0,
        )
    )
    for product in products:
        last = product.last_auto_run_at
        if last is not None:
            if last.tzinfo is None:  # SQLite 등에서 naive로 돌아오면 UTC로 간주
                last = last.replace(tzinfo=timezone.utc)
            if (now - last).total_seconds() < product.auto_interval_seconds:
                continue
        pending_prep = session.scalar(
            select(Job.id)
            .where(
                Job.product_id == product.id,
                Job.kind.in_(_PREP_KIND_VALUES),
                Job.status.not_in(_TERMINAL_VALUES),
            )
            .limit(1)
        )
        if pending_prep is not None:
            continue
        # diff를 먼저 만들어 id를 작게 → claim이 diff부터 집는다(변경 감지 후 누락 스캔)
        for kind in (JobKind.AUTO_DIFF, JobKind.AUTO_SCAN):
            job = Job(
                product_id=product.id,
                kind=kind.value,
                origin=JobOrigin.AUTO.value,
                file_list=[],
                excluded_files=[],
                status=JobStatus.QUEUED.value,
            )
            session.add(job)
            session.flush()
            created.append(job.id)
        product.last_auto_run_at = now
    session.commit()
    return created


def claim_prep_jobs(session: Session) -> list[int]:
    """실행 가능한 queued 준비 job을 프로덕트 이름당 1개씩 running으로 전이한다."""
    busy_names = set(
        session.scalars(
            select(Product.name).join(ProductLock, ProductLock.product_id == Product.id)
        )
    )
    busy_names |= set(
        session.scalars(
            select(Product.name)
            .join(Job, Job.product_id == Product.id)
            .where(
                Job.status == JobStatus.RUNNING.value,
                Job.kind.in_(_PREP_KIND_VALUES),
            )
        )
    )
    candidates = session.execute(
        select(Job, Product.name)
        .join(Product, Product.id == Job.product_id)
        .where(
            Job.status == JobStatus.QUEUED.value,
            Job.kind.in_(_PREP_KIND_VALUES),
        )
        .order_by(Job.id.asc())
    ).all()

    picked: list[int] = []
    for job, name in candidates:
        if name in busy_names:
            continue
        busy_names.add(name)
        job.status = JobStatus.RUNNING.value
        job.started_at = _utcnow()
        picked.append(job.id)
    session.commit()
    return picked


def _finish_prep(
    session: Session,
    job: Job,
    status: JobStatus,
    result_summary: str | None = None,
    error: str | None = None,
) -> None:
    """준비 job 종료 처리. 락·워커는 건드리지 않는다(준비 job은 어느 쪽도 안 쓴다)."""
    job.status = status.value
    job.finished_at = _utcnow()
    if result_summary is not None:
        job.result_summary = result_summary
    if error is not None:
        job.error = error
    session.commit()


def process_prep_job(session: Session, job_id: int) -> None:
    """running 준비 job 1건을 실행하고 done/failed/canceled로 종료한다."""
    job = session.get(Job, job_id)
    if job is None or job.status != JobStatus.RUNNING.value:
        return
    phase = JobPhase.DIFF.value if job.kind == JobKind.AUTO_DIFF.value else JobPhase.SCAN.value
    log_path = workspace.job_log_path(job_id)

    # runner/worker.py의 emit과 동일: (1) JobEvent → 모니터링 실시간 로그,
    # (2) job.log append → 진행 중 다운로드.
    def emit(ev_phase: str, level: str, message: str) -> None:
        text = message or ""
        session.add(JobEvent(job_id=job_id, level=level, phase=ev_phase, message=text[:8000]))
        session.commit()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"[{ev_phase}] {text}\n")
        except OSError:
            pass

    product = session.get(Product, job.product_id)
    if product is None:
        _finish_prep(session, job, JobStatus.FAILED, error="프로덕트 없음")
        return

    kind_label = "변경 감지" if job.kind == JobKind.AUTO_DIFF.value else "누락 테스트 스캔"
    emit(phase, "info", f"auto {kind_label} 시작: product={product.name}")

    summary: str | None = None
    run_error: Exception | None = None
    try:
        should_cancel = lambda: process_registry.is_canceled(job_id)  # noqa: E731
        if job.kind == JobKind.AUTO_DIFF.value:
            from genut_service.config import get_settings

            summary = auto_run_service.run_diff_job(
                session,
                job,
                product,
                emit,
                git_timeout=get_settings().git_timeout,
                should_cancel=should_cancel,
            )
        else:
            summary = auto_run_service.run_scan_job(
                session, job, product, emit, should_cancel=should_cancel
            )
    except Exception as exc:  # noqa: BLE001 - 어떤 예외든 이 job만 격리해 종료시킨다
        run_error = exc

    # 취소 판정은 unregister 전에 한다(unregister가 취소 플래그를 지운다)
    canceled = process_registry.is_canceled(job_id)
    process_registry.unregister(job_id)
    if canceled or isinstance(run_error, auto_run_service.AutoRunCanceled):
        emit(phase, "error", "강제 종료됨 (사용자 요청)")
        _finish_prep(session, job, JobStatus.CANCELED, error="사용자에 의해 강제 종료됨")
    elif run_error is not None:
        emit(phase, "error", f"{kind_label} 실패: {run_error}")
        _finish_prep(session, job, JobStatus.FAILED, error=str(run_error)[:2000])
    else:
        emit(phase, "info", f"완료: {summary}")
        _finish_prep(session, job, JobStatus.DONE, result_summary=summary)


def run_auto_pending(session: Session, now: datetime | None = None) -> int:
    """테스트/E2E용 결정론 헬퍼: 사이클 큐잉 후 준비 job을 다 소진할 때까지 처리한다.

    (loop.run_pending과 대칭. diff → scan 순서로 같은 호출 안에서 모두 처리된다.)
    """
    enqueue_due_cycles(session, now=now)
    processed = 0
    while True:
        picked = claim_prep_jobs(session)
        if not picked:
            break
        for job_id in picked:
            process_prep_job(session, job_id)
        processed += len(picked)
    return processed
