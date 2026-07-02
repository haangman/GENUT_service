"""워커 상태 및 요청 큐 조회."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, ProductLock
from genut_service.enums import JobKind, JobStatus


def list_workers(session: Session) -> list[GenutInstance]:
    return list(session.scalars(select(GenutInstance).order_by(GenutInstance.id)))


def list_queue(session: Session) -> list[tuple[Job, bool]]:
    """queued GENUT job을 순서대로 반환. 각 job의 프로덕트가 락 중이면 waiting=True.

    준비(auto_scan/auto_diff) job은 워커 큐가 아니라 스케줄러 auto 단계가 실행하므로
    워커 큐 뷰에서 제외한다.
    """
    locked = set(session.scalars(select(ProductLock.product_id)))
    jobs = session.scalars(
        select(Job)
        .where(
            Job.status == JobStatus.QUEUED.value,
            Job.kind == JobKind.GENUT.value,
        )
        .order_by(Job.priority.desc(), Job.submitted_at.asc(), Job.id.asc())
    )
    return [(job, job.product_id in locked) for job in jobs]
