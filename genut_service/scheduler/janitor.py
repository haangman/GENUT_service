"""stale 락/워커 정리. 스케줄러 시작 시 및 주기적으로 호출한다."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, ProductLock
from genut_service.enums import INFLIGHT_STATUSES, TERMINAL_STATUSES, JobStatus, WorkerStatus
from genut_service.scheduler.engine import finish_job

_TERMINAL = {status.value for status in TERMINAL_STATUSES}
_INFLIGHT = {status.value for status in INFLIGHT_STATUSES}


def reap_stuck_jobs(session: Session, max_runtime_seconds: float) -> int:
    """started_at가 max_runtime_seconds를 넘긴 in-flight(running 등) job을 회수한다. 처리 수 반환.

    **주기적 안전망**이다. 정상 job은 자신의 타임아웃(genut_run_timeout/git_timeout) 안에
    끝나므로, 이 상한을 넘긴 건 워커 스레드가 finish 없이 사라져 고착된 경우로 본다. FAILED로
    종료하고 락/워커를 회수한다. 상한은 정상 장기 job을 잘못 죽이지 않도록 넉넉히 잡는다.
    """
    now = datetime.now(timezone.utc)
    stuck_ids: list[int] = []
    for job in session.scalars(select(Job).where(Job.status.in_(_INFLIGHT))):
        started = job.started_at
        if started is None:
            continue
        if started.tzinfo is None:  # SQLite 등에서 naive로 돌아오면 UTC로 간주
            started = started.replace(tzinfo=timezone.utc)
        if (now - started).total_seconds() > max_runtime_seconds:
            stuck_ids.append(job.id)
    for job_id in stuck_ids:
        finish_job(
            session,
            job_id,
            JobStatus.FAILED,
            error="실행이 비정상적으로 오래 지속되어 회수됨 (watchdog)",
        )
    return len(stuck_ids)


def mark_interrupted_jobs(session: Session) -> int:
    """실행 도중 끊긴 job(running 등 in-flight)을 interrupted로 종료 처리한다. 처리 수 반환.

    **스케줄러 기동 시 1회만** 호출해야 한다(정상 실행 중인 job을 죽이지 않도록). 인앱
    스케줄러는 단일 프로세스이므로, 기동 시점에 DB에 남아 있는 in-flight job은 모두 이전
    프로세스(서버 재시작 전)가 남긴 고아 job이다. interrupted(terminal)로 바꾸고
    finished_at·사유를 기록한다. 락 해제/워커 idle 복구는 이어지는 release_stale_locks가
    처리한다(interrupted는 terminal이므로).
    """
    now = datetime.now(timezone.utc)
    count = 0
    for job in session.scalars(select(Job).where(Job.status.in_(_INFLIGHT))):
        job.status = JobStatus.INTERRUPTED.value
        job.finished_at = now
        job.error = "서버 재시작으로 실행이 중단됨"
        count += 1
    session.commit()
    return count


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
