"""stale 락/워커 정리. 스케줄러 시작 시 및 주기적으로 호출한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, JobEvent, ProductLock
from genut_service.enums import INFLIGHT_STATUSES, TERMINAL_STATUSES, JobStatus, WorkerStatus
from genut_service.runner import process_registry
from genut_service.scheduler.engine import finish_job

_TERMINAL = {status.value for status in TERMINAL_STATUSES}
_INFLIGHT = {status.value for status in INFLIGHT_STATUSES}


def reap_stuck_jobs(session: Session, max_runtime_seconds: float) -> int:
    """started_at가 max_runtime_seconds를 넘긴 in-flight(running 등) job을 회수한다. 처리 수 반환.

    **주기적 안전망**이다. 정상 job은 자신의 타임아웃(genut_run_timeout/git_timeout) 안에
    끝나므로, 이 상한을 넘긴 건 워커 스레드가 finish 없이 사라져 고착된 경우로 본다. FAILED로
    종료하고 락/워커를 회수한다. 상한은 정상 장기 job을 잘못 죽이지 않도록 넉넉히 잡는다.

    단, 그 job의 서브프로세스가 아직 레지스트리에 살아 있으면 **느린 정상 실행**으로 보고
    회수하지 않는다 — 살아있는 워커를 회수하면 락이 조기 해제되어 같은 프로덕트에 다른
    job이 배정되고, 같은 체크아웃에서 실행이 겹치는 경합이 생기기 때문이다(각 서브프로세스는
    자기 타임아웃으로 언젠가 끝난다).

    다만 상한의 **2배**를 넘기면 서브프로세스가 살아 있어도 하드캡으로 회수한다 —
    워커 스레드가 죽거나 멈춘 채 잔존 프로세스만 살아 있으면(예: 파이프를 쥔 고아
    빌드) 유예가 영원히 끝나지 않기 때문이다. 이때 등록된 프로세스 트리를 강제
    종료한 뒤 회수한다.
    """
    now = datetime.now(timezone.utc)
    stuck_ids: list[int] = []
    for job in session.scalars(select(Job).where(Job.status.in_(_INFLIGHT))):
        started = job.started_at
        if started is None:
            continue
        if started.tzinfo is None:  # SQLite 등에서 naive로 돌아오면 UTC로 간주
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (now - started).total_seconds()
        if elapsed <= max_runtime_seconds:
            continue
        if process_registry.has_process(job.id) and elapsed <= max_runtime_seconds * 2:
            continue  # 서브프로세스 생존 → 하드캡 전까지는 느린 실행으로 유예
        stuck_ids.append(job.id)
    for job_id in stuck_ids:
        # 잔존 프로세스 트리가 있으면 강제 종료(취소 플래그도 세워 워커가 깨어나면
        # CANCELED/no-op으로 정리되게 한다 — finish_job의 터미널 가드가 이중 종료를 막는다)
        process_registry.cancel(job_id)
        finish_job(
            session,
            job_id,
            JobStatus.FAILED,
            error="실행이 비정상적으로 오래 지속되어 회수됨 (watchdog)",
        )
        # 걸린 워커 스레드가 없을 수 있으므로 레지스트리 항목은 직접 정리한다
        process_registry.unregister(job_id)
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


def purge_old_job_events(session: Session, retention_days: int) -> int:
    """보존 기간을 넘긴 **종료된** job의 이벤트 로그를 삭제한다. 삭제 행 수 반환.

    JobEvent는 GENUT 출력 한 줄당 1행(append-only)이라 정리 없이는 무한 증가해
    로그 폴링·백업 비용을 계속 키운다. 전체 로그는 job.log 파일로 남아 다운로드는
    계속 동작한다. retention_days <= 0이면 아무것도 하지 않는다.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    old_jobs = (
        select(Job.id)
        .where(
            Job.status.in_(_TERMINAL),
            Job.finished_at.is_not(None),
            Job.finished_at < cutoff,
        )
        .scalar_subquery()
    )
    result = session.execute(delete(JobEvent).where(JobEvent.job_id.in_(old_jobs)))
    session.commit()
    return int(result.rowcount or 0)


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
