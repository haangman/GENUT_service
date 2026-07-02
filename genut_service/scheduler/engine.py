"""스케줄러 코어: 큐잉된 job을 idle 워커에 배정(claim)하고 완료 처리(finish)한다.

단일 writer(스케줄러)만 이 함수를 호출한다는 전제로, 동기/결정론적으로 동작한다.
배타성 불변식:
- 한 프로덕트는 동시에 1개 job만 (product_locks PK).
- N개 idle 워커 → 서로 다른 N개 프로덕트까지 동시 배정.
- 같은 프로덕트의 대기 job은 락 해제 후 다음 tick에 배정된다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import PREP_KINDS, JobKind, JobStatus, WorkerStatus
from genut_service.scheduler.lock import release_lock, try_acquire_lock

_PREP_KIND_VALUES = tuple(kind.value for kind in PREP_KINDS)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def claim_jobs(session: Session) -> list[tuple[int, int]]:
    """idle 워커에 배정 가능한 queued job을 배정한다.

    반환: [(job_id, genut_instance_id), ...]. 배정된 job은 status=running,
    워커는 busy, product_locks에 락이 생긴다.
    """
    idle_workers = list(
        session.scalars(
            select(GenutInstance).where(
                GenutInstance.enabled.is_(True),
                GenutInstance.worker_status == WorkerStatus.IDLE.value,
            )
        )
    )
    if not idle_workers:
        return []

    # 배타는 프로덕트 "이름" 기준이다. 같은 이름의 프로덕트(다른 id)끼리도 동시에 돌지 않는다.
    busy_names = set(
        session.scalars(
            select(Product.name).join(ProductLock, ProductLock.product_id == Product.id)
        )
    )
    # auto 준비(auto_scan/auto_diff) job이 실행 중인 프로덕트도 배타 — 준비 작업의
    # git reset(제자리 갱신)과 GENUT 실행이 같은 체크아웃에서 충돌하지 않게 한다.
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
        # 워커는 GENUT job만 집는다. 준비(auto_scan/auto_diff) job은 스케줄러의
        # auto 단계가 직접 실행한다.
        .where(
            Job.status == JobStatus.QUEUED.value,
            Job.kind == JobKind.GENUT.value,
        )
        .order_by(Job.priority.desc(), Job.submitted_at.asc(), Job.id.asc())
    ).all()

    # 락이 없는 이름부터, 같은 이름당 1개씩만 후보로 뽑는다
    eligible: list[Job] = []
    seen_names = set(busy_names)
    for job, name in candidates:
        if name in seen_names:
            continue
        seen_names.add(name)
        eligible.append(job)

    assignments: list[tuple[int, int]] = []
    for worker, job in zip(idle_workers, eligible):
        if not try_acquire_lock(session, job.product_id, job.id, worker.id):
            continue
        job.status = JobStatus.RUNNING.value
        job.genut_instance_id = worker.id
        job.started_at = _utcnow()
        worker.worker_status = WorkerStatus.BUSY.value
        worker.current_job_id = job.id
        assignments.append((job.id, worker.id))

    session.commit()
    return assignments


def finish_job(
    session: Session,
    job_id: int,
    status: JobStatus,
    result_summary: str | None = None,
    error: str | None = None,
) -> None:
    """job을 종료 처리하고 락 해제 + 워커를 idle로 되돌린다."""
    job = session.get(Job, job_id)
    if job is None:
        return
    job.status = status.value
    job.finished_at = _utcnow()
    if result_summary is not None:
        job.result_summary = result_summary
    if error is not None:
        job.error = error

    release_lock(session, job.product_id)

    if job.genut_instance_id is not None:
        worker = session.get(GenutInstance, job.genut_instance_id)
        if worker is not None and worker.current_job_id == job.id:
            worker.worker_status = WorkerStatus.IDLE.value
            worker.current_job_id = None

    session.commit()
