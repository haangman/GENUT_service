"""auto 모드: 스케줄러 주기 사이클(enqueue/claim/process) 및 배타/janitor 테스트."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, JobEvent, Product, ProductLock
from genut_service.enums import JobKind, JobOrigin, JobStatus, WorkerStatus
from genut_service.runner import process_registry
from genut_service.scheduler import auto_tick
from genut_service.scheduler.engine import claim_jobs
from genut_service.scheduler.janitor import mark_interrupted_jobs, reap_stuck_jobs

AAA_SOURCE = (
    "int bbb(void) { return 1; }\n"
    "int ccc(void) { return 2; }\n"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_root(tmp_path: Path, git: bool = False) -> Path:
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "aaa.c").write_text(AAA_SOURCE, encoding="utf-8")
    (root / "build").mkdir(parents=True, exist_ok=True)
    compdb = [
        {
            "directory": str(root / "build"),
            "command": "cc -c",
            "file": str((root / "src" / "aaa.c").resolve()),
        }
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    if git:
        for args in (
            ["init", "-b", "main"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "tester"],
            ["add", "-A"],
            ["commit", "-m", "init"],
        ):
            subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=True,
            )
    return root


def _auto_product(
    session: Session,
    name: str = "autoP",
    interval: int = 60,
    code_path: str | None = None,
    active: bool = True,
    auto_run: bool = True,
) -> Product:
    product = Product(
        name=name,
        product_code=name,
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="unittests",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="c",
        active=active,
        auto_run=auto_run,
        auto_interval_seconds=interval,
        auto_file_list=["src/aaa.c"],
        code_path=code_path,
    )
    session.add(product)
    session.commit()
    return product


def _worker(session: Session, name: str = "w1") -> GenutInstance:
    worker = GenutInstance(
        name=name,
        repo_url="u",
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
        worker_status=WorkerStatus.IDLE.value,
    )
    session.add(worker)
    session.commit()
    return worker


def _jobs(session: Session, kind: JobKind | None = None) -> list[Job]:
    stmt = select(Job).order_by(Job.id)
    if kind is not None:
        stmt = stmt.where(Job.kind == kind.value)
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# enqueue_due_cycles
# ---------------------------------------------------------------------------


def test_enqueue_creates_diff_then_scan_pair_and_stamps_time(db_session: Session) -> None:
    product = _auto_product(db_session)
    created = auto_tick.enqueue_due_cycles(db_session)

    jobs = _jobs(db_session)
    assert [j.id for j in jobs] == created
    assert [j.kind for j in jobs] == [JobKind.AUTO_DIFF.value, JobKind.AUTO_SCAN.value]
    assert all(j.origin == JobOrigin.AUTO.value for j in jobs)
    assert all(j.status == JobStatus.QUEUED.value for j in jobs)
    assert product.last_auto_run_at is not None


def test_enqueue_respects_interval(db_session: Session) -> None:
    product = _auto_product(db_session, interval=60)
    product.last_auto_run_at = _now() - timedelta(seconds=30)
    db_session.commit()
    assert auto_tick.enqueue_due_cycles(db_session) == []  # 주기 미도래

    product.last_auto_run_at = _now() - timedelta(seconds=61)
    db_session.commit()
    assert len(auto_tick.enqueue_due_cycles(db_session)) == 2  # 도래


def test_enqueue_skips_while_previous_cycle_pending(db_session: Session) -> None:
    product = _auto_product(db_session)
    auto_tick.enqueue_due_cycles(db_session)

    # 주기를 강제로 도래시켜도, 이전 사이클 준비 job이 비종료면 스킵
    forced_past = _now() - timedelta(seconds=999)
    product.last_auto_run_at = forced_past
    db_session.commit()
    assert auto_tick.enqueue_due_cycles(db_session) == []
    assert len(_jobs(db_session)) == 2

    # 이전 사이클을 종료시키면 새 사이클이 큐잉되고 시각이 현재로 갱신된다
    # (시계 해상도가 낮은 환경에서도 결정적이도록 강제 과거값과 비교한다)
    for job in _jobs(db_session):
        job.status = JobStatus.DONE.value
    db_session.commit()
    assert len(auto_tick.enqueue_due_cycles(db_session)) == 2
    assert product.last_auto_run_at > forced_past


def test_enqueue_skips_non_auto_inactive_and_no_interval(db_session: Session) -> None:
    _auto_product(db_session, name="off", auto_run=False)
    _auto_product(db_session, name="inactive", active=False)
    _auto_product(db_session, name="no-interval", interval=0)
    p = _auto_product(db_session, name="none-interval")
    p.auto_interval_seconds = None
    db_session.commit()

    assert auto_tick.enqueue_due_cycles(db_session) == []


def test_enqueue_cycle_now_ignores_interval(db_session: Session) -> None:
    """수동 실행은 주기가 도래하지 않아도 사이클 쌍을 즉시 큐잉한다."""
    product = _auto_product(db_session, interval=3600)
    product.last_auto_run_at = _now()  # 방금 실행됨 → 주기상으로는 한참 남음
    db_session.commit()
    stamp_before = product.last_auto_run_at

    created = auto_tick.enqueue_cycle_now(db_session, product)

    jobs = _jobs(db_session)
    assert [j.id for j in jobs] == created
    assert [j.kind for j in jobs] == [JobKind.AUTO_DIFF.value, JobKind.AUTO_SCAN.value]
    assert all(j.status == JobStatus.QUEUED.value for j in jobs)
    assert product.last_auto_run_at >= stamp_before  # 기산점이 지금으로 갱신


def test_enqueue_cycle_now_skips_while_cycle_pending(db_session: Session) -> None:
    product = _auto_product(db_session)
    assert len(auto_tick.enqueue_cycle_now(db_session, product)) == 2
    # 이전 사이클 준비 job이 비종료인 동안은 중복 사이클을 만들지 않는다
    assert auto_tick.enqueue_cycle_now(db_session, product) == []
    assert len(_jobs(db_session)) == 2


# ---------------------------------------------------------------------------
# claim_prep_jobs (배타·순서)
# ---------------------------------------------------------------------------


def test_claim_prep_runs_diff_first_one_per_product(db_session: Session) -> None:
    _auto_product(db_session)
    auto_tick.enqueue_due_cycles(db_session)

    picked = auto_tick.claim_prep_jobs(db_session)
    jobs = _jobs(db_session)
    assert picked == [jobs[0].id]  # diff(작은 id)만 running
    assert jobs[0].kind == JobKind.AUTO_DIFF.value
    assert jobs[0].status == JobStatus.RUNNING.value
    assert jobs[1].status == JobStatus.QUEUED.value  # scan은 대기

    # running 준비 job이 있는 동안은 같은 프로덕트의 scan을 집지 않는다
    assert auto_tick.claim_prep_jobs(db_session) == []

    jobs[0].status = JobStatus.DONE.value
    db_session.commit()
    assert auto_tick.claim_prep_jobs(db_session) == [jobs[1].id]


def test_claim_prep_defers_when_product_locked(db_session: Session) -> None:
    product = _auto_product(db_session)
    worker = _worker(db_session)
    genut_job = Job(product_id=product.id, status=JobStatus.RUNNING.value)
    db_session.add(genut_job)
    db_session.flush()
    db_session.add(
        ProductLock(product_id=product.id, job_id=genut_job.id, genut_instance_id=worker.id)
    )
    db_session.commit()
    auto_tick.enqueue_due_cycles(db_session)

    assert auto_tick.claim_prep_jobs(db_session) == []  # GENUT 실행 중 → 연기
    db_session.delete(db_session.get(ProductLock, product.id))
    db_session.commit()
    assert len(auto_tick.claim_prep_jobs(db_session)) == 1  # 락 해제 후 집는다


def test_claim_prep_is_exclusive_by_product_name(db_session: Session) -> None:
    # 같은 이름의 두 프로덕트(변이) — 준비 job도 이름 기준으로 동시에 1개만
    _auto_product(db_session, name="SAME")
    _auto_product(db_session, name="SAME")
    auto_tick.enqueue_due_cycles(db_session)

    picked = auto_tick.claim_prep_jobs(db_session)
    assert len(picked) == 1


def test_claim_jobs_excludes_products_with_running_prep(db_session: Session) -> None:
    product = _auto_product(db_session)
    _worker(db_session)
    db_session.add(Job(product_id=product.id))  # queued GENUT job
    db_session.commit()
    auto_tick.enqueue_due_cycles(db_session)
    auto_tick.claim_prep_jobs(db_session)  # diff가 running

    assert claim_jobs(db_session) == []  # 준비 job 실행 중 → GENUT 배정 금지

    for job in _jobs(db_session, JobKind.AUTO_DIFF):
        job.status = JobStatus.DONE.value
    for job in _jobs(db_session, JobKind.AUTO_SCAN):
        job.status = JobStatus.DONE.value
    db_session.commit()
    assert len(claim_jobs(db_session)) == 1  # 준비 종료 후 배정 재개


# ---------------------------------------------------------------------------
# process_prep_job
# ---------------------------------------------------------------------------


def _claimed_prep(
    session: Session, product: Product, kind: JobKind
) -> Job:
    job = Job(
        product_id=product.id,
        kind=kind.value,
        origin=JobOrigin.AUTO.value,
        status=JobStatus.RUNNING.value,
        started_at=_now(),
    )
    session.add(job)
    session.commit()
    return job


def test_process_scan_job_completes_and_queues_genut_job(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    product = _auto_product(db_session, code_path=str(root))
    scan = _claimed_prep(db_session, product, JobKind.AUTO_SCAN)

    auto_tick.process_prep_job(db_session, scan.id)

    db_session.refresh(scan)
    assert scan.status == JobStatus.DONE.value
    assert "job 1개 생성" in (scan.result_summary or "")
    genut_jobs = _jobs(db_session, JobKind.GENUT)
    assert [(j.file_list, j.function_name) for j in genut_jobs] == [(["src/aaa.c"], None)]
    events = list(db_session.scalars(select(JobEvent).where(JobEvent.job_id == scan.id)))
    assert events  # 진행 로그(JobEvent)가 남는다


def test_process_diff_job_records_baseline(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path, git=True)
    product = _auto_product(db_session, code_path=str(root))
    diff = _claimed_prep(db_session, product, JobKind.AUTO_DIFF)

    auto_tick.process_prep_job(db_session, diff.id)

    db_session.refresh(diff)
    assert diff.status == JobStatus.DONE.value
    assert product.last_scanned_commit is not None


def test_process_prep_job_without_code_path_fails_with_reason(
    db_session: Session,
) -> None:
    product = _auto_product(db_session, code_path=None)
    scan = _claimed_prep(db_session, product, JobKind.AUTO_SCAN)

    auto_tick.process_prep_job(db_session, scan.id)

    db_session.refresh(scan)
    assert scan.status == JobStatus.FAILED.value
    assert "code_path" in (scan.error or "")


def test_process_prep_job_canceled_by_user(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    product = _auto_product(db_session, code_path=str(root))
    scan = _claimed_prep(db_session, product, JobKind.AUTO_SCAN)

    process_registry.cancel(scan.id)  # 취소 플래그 세팅(프로세스 없음 → False 반환 무시)
    try:
        auto_tick.process_prep_job(db_session, scan.id)
    finally:
        process_registry.unregister(scan.id)

    db_session.refresh(scan)
    assert scan.status == JobStatus.CANCELED.value


def test_process_prep_job_survives_event_write_failure(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    """JobEvent 기록이 계속 실패해도 job이 running 고아로 남지 않는다(최후 폴백)."""
    root = _make_root(tmp_path)
    product = _auto_product(db_session, code_path=str(root))
    scan = _claimed_prep(db_session, product, JobKind.AUTO_SCAN)

    class BoomEvent:  # 모든 emit이 예외를 던지는 상황 모사(DB 잠금 경합 등)
        def __init__(self, *args, **kwargs):
            raise RuntimeError("event write failed")

    monkeypatch.setattr(auto_tick, "JobEvent", BoomEvent)

    auto_tick.process_prep_job(db_session, scan.id)

    db_session.expire_all()
    reloaded = db_session.get(Job, scan.id)
    assert reloaded.status == JobStatus.FAILED.value  # 고아(running) 잔류 금지
    assert "종료 처리 실패" in (reloaded.error or "")


def test_process_prep_job_passes_cancel_hooks_to_diff(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    """diff 실행에 취소 플래그 확인·서브프로세스 등록 콜백이 전달된다."""
    captured: dict = {}

    def fake_diff(session, job, product, emit, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(auto_tick.auto_run_service, "run_diff_job", fake_diff)
    root = _make_root(tmp_path)
    product = _auto_product(db_session, code_path=str(root))
    diff = _claimed_prep(db_session, product, JobKind.AUTO_DIFF)

    auto_tick.process_prep_job(db_session, diff.id)

    assert callable(captured.get("should_cancel"))
    assert callable(captured.get("on_process"))


def test_process_prep_job_ignores_non_running(db_session: Session) -> None:
    product = _auto_product(db_session)
    job = Job(
        product_id=product.id,
        kind=JobKind.AUTO_SCAN.value,
        origin=JobOrigin.AUTO.value,
        status=JobStatus.QUEUED.value,
    )
    db_session.add(job)
    db_session.commit()

    auto_tick.process_prep_job(db_session, job.id)  # running이 아니면 무시

    db_session.refresh(job)
    assert job.status == JobStatus.QUEUED.value


# ---------------------------------------------------------------------------
# janitor가 준비 job도 커버한다
# ---------------------------------------------------------------------------


def test_janitor_reaps_stuck_prep_job(db_session: Session) -> None:
    product = _auto_product(db_session)
    prep = _claimed_prep(db_session, product, JobKind.AUTO_SCAN)
    prep.started_at = _now() - timedelta(hours=10)
    db_session.commit()

    assert reap_stuck_jobs(db_session, max_runtime_seconds=60) == 1
    db_session.refresh(prep)
    assert prep.status == JobStatus.FAILED.value


def test_janitor_marks_interrupted_prep_job(db_session: Session) -> None:
    product = _auto_product(db_session)
    prep = _claimed_prep(db_session, product, JobKind.AUTO_DIFF)

    assert mark_interrupted_jobs(db_session) == 1
    db_session.refresh(prep)
    assert prep.status == JobStatus.INTERRUPTED.value


# ---------------------------------------------------------------------------
# run_auto_pending (결정론 미니 e2e)
# ---------------------------------------------------------------------------


def test_run_auto_pending_processes_full_cycle(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path, git=True)
    product = _auto_product(db_session, code_path=str(root))

    processed = auto_tick.run_auto_pending(db_session)

    assert processed == 2  # diff → scan 순으로 모두 처리
    prep_jobs = [j for j in _jobs(db_session) if j.kind != JobKind.GENUT.value]
    assert [j.kind for j in prep_jobs] == [JobKind.AUTO_DIFF.value, JobKind.AUTO_SCAN.value]
    assert all(j.status == JobStatus.DONE.value for j in prep_jobs)
    assert product.last_scanned_commit is not None  # diff: 최초 기준 기록
    genut_jobs = _jobs(db_session, JobKind.GENUT)
    assert len(genut_jobs) == 1  # scan: 테스트 없음 → 파일 단위 job
    assert genut_jobs[0].origin == JobOrigin.AUTO.value


# ---------------------------------------------------------------------------
# Scheduler 백그라운드 루프 통합
# ---------------------------------------------------------------------------


def test_scheduler_loop_runs_auto_cycle(tmp_path: Path) -> None:
    import asyncio

    from genut_service.db.base import Base, make_engine, make_session_factory
    from genut_service.scheduler.loop import Scheduler

    engine = make_engine(f"sqlite:///{(tmp_path / 'auto_loop.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)

    root = _make_root(tmp_path, git=True)
    with session_factory() as session:
        _auto_product(session, code_path=str(root))

    async def run() -> None:
        scheduler = Scheduler(session_factory, interval=0.05)
        await scheduler.start()
        for _ in range(200):
            with session_factory() as session:
                prep_done = [
                    j.status == JobStatus.DONE.value
                    for j in _jobs(session)
                    if j.kind != JobKind.GENUT.value
                ]
                genut_count = len(_jobs(session, JobKind.GENUT))
            if len(prep_done) == 2 and all(prep_done) and genut_count == 1:
                break
            await asyncio.sleep(0.05)
        await scheduler.stop()

    asyncio.run(run())

    with session_factory() as session:
        prep_jobs = [j for j in _jobs(session) if j.kind != JobKind.GENUT.value]
        assert [j.kind for j in prep_jobs] == [
            JobKind.AUTO_DIFF.value,
            JobKind.AUTO_SCAN.value,
        ]
        assert all(j.status == JobStatus.DONE.value for j in prep_jobs)
        assert len(_jobs(session, JobKind.GENUT)) == 1  # scan이 파일 단위 job을 큐잉
    engine.dispose()
