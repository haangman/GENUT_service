"""stale 락/워커 정리. 스케줄러 시작 시 및 주기적으로 호출한다."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, ProductLock
from genut_service.enums import TERMINAL_STATUSES, WorkerStatus

_TERMINAL = {status.value for status in TERMINAL_STATUSES}


def release_stale_locks(session: Session) -> int:
    """job이 종료(또는 소실)된 락을 해제하고, 그런 job을 쥔 busy 워커를 idle로 되돌린다."""
    released = 0
    for lock in list(session.scalars(select(ProductLock))):
        job = session.get(Job, lock.job_id)
        if job is None or job.status in _TERMINAL:
            session.delete(lock)
            released += 1

    busy_workers = session.scalars(
        select(GenutInstance).where(GenutInstance.worker_status == WorkerStatus.BUSY.value)
    )
    for worker in busy_workers:
        job = session.get(Job, worker.current_job_id) if worker.current_job_id else None
        if job is None or job.status in _TERMINAL:
            worker.worker_status = WorkerStatus.IDLE.value
            worker.current_job_id = None

    session.commit()
    return released
