"""M9: 워커/큐 모니터링 + stale-lock janitor 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import JobStatus, WorkerStatus
from genut_service.scheduler.engine import claim_jobs
from genut_service.scheduler.janitor import (
    mark_interrupted_jobs,
    reap_stuck_jobs,
    release_stale_locks,
)


def _product(session: Session, name: str = "P") -> Product:
    product = Product(
        name=name, product_code=name, git_url="u", compile_db_rel="build",
        out_tests_rel="tests", cmake_configure_cmd="c", cmake_build_cmd="b",
        test_run_cmd="r", test_generation_mode="cpp",
    )
    session.add(product)
    session.commit()
    return product


def _worker(session: Session, name: str = "w1") -> GenutInstance:
    worker = GenutInstance(
        name=name, repo_url="u", ds_assist_credential_key="k", ds_assist_send_system_name="s"
    )
    session.add(worker)
    session.commit()
    return worker


def test_workers_endpoint_lists_workers(client: TestClient, db_session: Session) -> None:
    _worker(db_session, "w1")
    resp = client.get("/api/workers")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["worker_status"] == "idle"


def test_queue_marks_waiting_on_busy_product(client: TestClient, db_session: Session) -> None:
    product = _product(db_session)
    _worker(db_session, "w1")
    db_session.add_all([Job(product_id=product.id), Job(product_id=product.id)])
    db_session.commit()

    claim_jobs(db_session)  # 1개 running(락), 1개 queued

    resp = client.get("/api/queue")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["waiting_on_product"] is True


def test_queue_excludes_prep_jobs(client: TestClient, db_session: Session) -> None:
    from genut_service.enums import JobKind, JobOrigin

    product = _product(db_session)
    db_session.add_all(
        [
            Job(product_id=product.id),  # GENUT queued → 노출
            Job(
                product_id=product.id,
                kind=JobKind.AUTO_SCAN.value,
                origin=JobOrigin.AUTO.value,
            ),
            Job(
                product_id=product.id,
                kind=JobKind.AUTO_DIFF.value,
                origin=JobOrigin.AUTO.value,
            ),
        ]
    )
    db_session.commit()

    body = client.get("/api/queue").json()
    assert len(body) == 1  # 준비(auto_scan/auto_diff) job은 워커 큐 뷰에서 제외


def test_queue_exposes_job_origin(client: TestClient, db_session: Session) -> None:
    from genut_service.enums import JobOrigin

    product = _product(db_session)
    db_session.add_all(
        [
            Job(product_id=product.id),  # 수동 제출(기본 manual)
            Job(product_id=product.id, origin=JobOrigin.AUTO.value),
        ]
    )
    db_session.commit()

    body = client.get("/api/queue").json()
    assert [item["origin"] for item in body] == ["manual", "auto"]


def test_janitor_releases_terminal_lock_and_resets_worker(db_session: Session) -> None:
    product = _product(db_session)
    worker = _worker(db_session)
    job = Job(product_id=product.id, status=JobStatus.DONE.value, genut_instance_id=worker.id)
    db_session.add(job)
    db_session.flush()
    worker.worker_status = WorkerStatus.BUSY.value
    worker.current_job_id = job.id
    db_session.add(ProductLock(product_id=product.id, job_id=job.id, genut_instance_id=worker.id))
    db_session.commit()

    released = release_stale_locks(db_session)
    assert released == 1
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 0
    db_session.expire_all()
    assert db_session.get(GenutInstance, worker.id).worker_status == WorkerStatus.IDLE.value


def test_mark_interrupted_jobs_marks_inflight_and_recovers(db_session: Session) -> None:
    """서버 재시작 시: in-flight job은 interrupted로 종료되고, 이어진 janitor가 락/워커를 회수한다."""
    product = _product(db_session)
    worker = _worker(db_session)
    running = Job(product_id=product.id, status=JobStatus.RUNNING.value, genut_instance_id=worker.id)
    queued = Job(product_id=product.id, status=JobStatus.QUEUED.value)
    done = Job(product_id=product.id, status=JobStatus.DONE.value)
    db_session.add_all([running, queued, done])
    db_session.flush()
    worker.worker_status = WorkerStatus.BUSY.value
    worker.current_job_id = running.id
    db_session.add(ProductLock(product_id=product.id, job_id=running.id, genut_instance_id=worker.id))
    db_session.commit()

    n = mark_interrupted_jobs(db_session)
    assert n == 1  # running 만 대상
    db_session.expire_all()
    assert db_session.get(Job, running.id).status == JobStatus.INTERRUPTED.value
    assert db_session.get(Job, running.id).finished_at is not None
    # queued/terminal job은 건드리지 않는다
    assert db_session.get(Job, queued.id).status == JobStatus.QUEUED.value
    assert db_session.get(Job, done.id).status == JobStatus.DONE.value

    # interrupted는 terminal이므로 release_stale_locks가 락 해제 + 워커 idle 복구
    release_stale_locks(db_session)
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 0
    db_session.expire_all()
    assert db_session.get(GenutInstance, worker.id).worker_status == WorkerStatus.IDLE.value


def test_reap_stuck_jobs_recovers_overlong_running(db_session: Session) -> None:
    """상한을 넘겨 고착된 running job은 회수(FAILED+락 해제+워커 idle)되고, 최근 건은 보존된다."""
    from datetime import datetime, timedelta, timezone

    product = _product(db_session)
    worker = _worker(db_session)
    old = Job(
        product_id=product.id,
        status=JobStatus.RUNNING.value,
        genut_instance_id=worker.id,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=10_000),
    )
    fresh = Job(
        product_id=product.id,
        status=JobStatus.RUNNING.value,
        started_at=datetime.now(timezone.utc),
    )
    db_session.add_all([old, fresh])
    db_session.flush()
    worker.worker_status = WorkerStatus.BUSY.value
    worker.current_job_id = old.id
    db_session.add(ProductLock(product_id=product.id, job_id=old.id, genut_instance_id=worker.id))
    db_session.commit()

    reaped = reap_stuck_jobs(db_session, max_runtime_seconds=3600)
    assert reaped == 1  # old만 회수
    db_session.expire_all()
    assert db_session.get(Job, old.id).status == JobStatus.FAILED.value
    assert db_session.get(Job, fresh.id).status == JobStatus.RUNNING.value  # 최근 건은 보존
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 0
    assert db_session.get(GenutInstance, worker.id).worker_status == WorkerStatus.IDLE.value


def test_reap_skips_job_with_live_subprocess(db_session: Session) -> None:
    """서브프로세스가 살아 등록된 job은 하드캡(2배) 전까지 느린 정상 실행으로 유예한다."""
    from datetime import datetime, timedelta, timezone

    from genut_service.runner import process_registry

    product = _product(db_session)
    job = Job(
        product_id=product.id,
        status=JobStatus.RUNNING.value,
        # 상한(60s)은 넘었지만 하드캡(120s)은 안 넘은 구간
        started_at=datetime.now(timezone.utc) - timedelta(seconds=90),
    )
    db_session.add(job)
    db_session.commit()

    class _FakeProc:
        pid = None

        def terminate(self) -> None: ...
        def kill(self) -> None: ...

    process_registry.register(job.id, _FakeProc())
    try:
        assert reap_stuck_jobs(db_session, max_runtime_seconds=60) == 0  # 생존 → 유예
        db_session.expire_all()
        assert db_session.get(Job, job.id).status == JobStatus.RUNNING.value
    finally:
        process_registry.unregister(job.id)

    # 서브프로세스가 사라지면(등록 해제) 죽은 워커로 보고 회수한다
    assert reap_stuck_jobs(db_session, max_runtime_seconds=60) == 1
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.FAILED.value


def test_reap_hard_cap_recovers_despite_live_subprocess(db_session: Session) -> None:
    """상한의 2배를 넘기면 잔존 프로세스가 있어도 트리를 죽이고 회수한다.

    워커 스레드가 멈춘 채 파이프를 쥔 고아 프로세스만 살아 있으면 유예가 영원히
    끝나지 않기 때문이다(회수 불가 → 그 프로덕트 영구 정지).
    """
    from datetime import datetime, timedelta, timezone

    from genut_service.runner import process_registry

    product = _product(db_session)
    job = Job(
        product_id=product.id,
        status=JobStatus.RUNNING.value,
        started_at=datetime.now(timezone.utc) - timedelta(seconds=10_000),  # 하드캡 초과
    )
    db_session.add(job)
    db_session.commit()

    kills: list[str] = []

    class _FakeProc:
        pid = None

        def terminate(self) -> None:
            kills.append("terminate")

        def kill(self) -> None:
            kills.append("kill")

    process_registry.register(job.id, _FakeProc())

    assert reap_stuck_jobs(db_session, max_runtime_seconds=60) == 1
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.FAILED.value
    assert kills  # 잔존 프로세스 트리 강제 종료 시도
    assert process_registry.has_process(job.id) is False  # 레지스트리 정리됨


def test_purge_old_job_events_removes_only_old_terminal(db_session: Session) -> None:
    """보존 기간을 넘긴 종료 job의 이벤트만 삭제된다(최근·실행 중 job은 보존)."""
    from datetime import datetime, timedelta, timezone

    from genut_service.db.models import JobEvent
    from genut_service.scheduler.janitor import purge_old_job_events

    product = _product(db_session)
    old_done = Job(
        product_id=product.id,
        status=JobStatus.DONE.value,
        finished_at=datetime.now(timezone.utc) - timedelta(days=20),
    )
    recent_done = Job(
        product_id=product.id,
        status=JobStatus.DONE.value,
        finished_at=datetime.now(timezone.utc),
    )
    running = Job(product_id=product.id, status=JobStatus.RUNNING.value)
    db_session.add_all([old_done, recent_done, running])
    db_session.flush()
    db_session.add_all(
        [
            JobEvent(job_id=old_done.id, message="old-1"),
            JobEvent(job_id=old_done.id, message="old-2"),
            JobEvent(job_id=recent_done.id, message="recent"),
            JobEvent(job_id=running.id, message="live"),
        ]
    )
    db_session.commit()

    assert purge_old_job_events(db_session, retention_days=14) == 2
    remaining = [e.message for e in db_session.scalars(select(JobEvent))]
    assert sorted(remaining) == ["live", "recent"]

    # retention_days <= 0 이면 비활성(아무것도 지우지 않는다)
    assert purge_old_job_events(db_session, retention_days=0) == 0
    assert db_session.scalar(select(func.count()).select_from(JobEvent)) == 2
