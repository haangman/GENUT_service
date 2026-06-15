"""워커 상태 및 요청 큐 조회."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, ProductLock
from genut_service.enums import JobStatus


def list_workers(session: Session) -> list[GenutInstance]:
    return list(session.scalars(select(GenutInstance).order_by(GenutInstance.id)))


def list_queue(session: Session) -> list[tuple[Job, bool]]:
    """queued job을 순서대로 반환. 각 job의 프로덕트가 락 중이면 waiting=True."""
    locked = set(session.scalars(select(ProductLock.product_id)))
    jobs = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.QUEUED.value)
        .order_by(Job.priority.desc(), Job.submitted_at.asc(), Job.id.asc())
    )
    return [(job, job.product_id in locked) for job in jobs]
