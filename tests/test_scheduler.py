"""M5: 스케줄러 claim/finish 동시성·배타 불변식 테스트 (결정론적, 스레드 없음)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import JobKind, JobStatus, WorkerStatus
from genut_service.scheduler.engine import claim_jobs, finish_job


def _product(session: Session, name: str) -> Product:
    product = Product(
        name=name,
        product_code=name,
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
    )
    session.add(product)
    session.commit()
    return product


def _worker(session: Session, name: str, enabled: bool = True) -> GenutInstance:
    worker = GenutInstance(
        name=name,
        repo_url="u",
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
        enabled=enabled,
        worker_status=WorkerStatus.IDLE.value,
    )
    session.add(worker)
    session.commit()
    return worker


def _job(session: Session, product_id: int) -> Job:
    job = Job(product_id=product_id)
    session.add(job)
    session.commit()
    return job


def _running_count_for_product(session: Session, product_id: int) -> int:
    return session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.product_id == product_id, Job.status == JobStatus.RUNNING.value)
    )


def test_same_product_is_not_double_claimed(db_session: Session) -> None:
    product = _product(db_session, "P")
    _worker(db_session, "w1")
    _worker(db_session, "w2")
    _job(db_session, product.id)
    _job(db_session, product.id)

    assignments = claim_jobs(db_session)
    assert len(assignments) == 1
    assert _running_count_for_product(db_session, product.id) == 1
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 1


def test_worker_cap_limits_distinct_products(db_session: Session) -> None:
    products = [_product(db_session, f"P{i}") for i in range(3)]
    _worker(db_session, "w1")
    _worker(db_session, "w2")
    for product in products:
        _job(db_session, product.id)

    assignments = claim_jobs(db_session)
    assert len(assignments) == 2  # 워커 2개 한도
    running = db_session.scalars(
        select(Job.product_id).where(Job.status == JobStatus.RUNNING.value)
    ).all()
    assert len(set(running)) == 2  # 서로 다른 프로덕트
    queued = db_session.scalar(
        select(func.count()).select_from(Job).where(Job.status == JobStatus.QUEUED.value)
    )
    assert queued == 1


def test_same_product_fan_in_serializes(db_session: Session) -> None:
    product = _product(db_session, "P")
    _worker(db_session, "w1")
    for _ in range(3):
        _job(db_session, product.id)

    done = 0
    for _ in range(5):
        assignments = claim_jobs(db_session)
        # 동시에 P에 대해 실행 중인 job은 항상 ≤ 1
        assert _running_count_for_product(db_session, product.id) <= 1
        if assignments:
            finish_job(db_session, assignments[0][0], JobStatus.DONE)
            done += 1
        if done == 3:
            break
    assert done == 3
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 0


def test_failure_isolation(db_session: Session) -> None:
    p1 = _product(db_session, "P1")
    p2 = _product(db_session, "P2")
    _worker(db_session, "w1")
    _worker(db_session, "w2")
    job1 = _job(db_session, p1.id)
    _job(db_session, p2.id)

    assignments = claim_jobs(db_session)
    assert len(assignments) == 2

    finish_job(db_session, job1.id, JobStatus.FAILED, error="boom")
    db_session.expire_all()

    assert db_session.get(Job, job1.id).status == JobStatus.FAILED.value
    assert db_session.get(ProductLock, p1.id) is None  # P1 락 해제
    assert db_session.get(ProductLock, p2.id) is not None  # P2 영향 없음
    assert _running_count_for_product(db_session, p2.id) == 1

    # P1 락이 풀렸으니 새 P1 job을 다시 배정할 수 있다
    new_job = _job(db_session, p1.id)
    again = claim_jobs(db_session)
    assert (new_job.id, ) in [(jid,) for jid, _ in again]


def test_same_name_products_are_mutually_exclusive(db_session: Session) -> None:
    # 이름이 같은 두 프로덕트(다른 id)는 동시에 실행되지 않는다
    p1 = _product(db_session, "SAME")
    p2 = _product(db_session, "SAME")
    assert p1.id != p2.id
    _worker(db_session, "w1")
    _worker(db_session, "w2")
    _job(db_session, p1.id)
    _job(db_session, p2.id)

    assignments = claim_jobs(db_session)
    assert len(assignments) == 1  # 같은 이름 → 동시에 1개만
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 1

    # 첫 job이 끝나면 같은 이름의 다른 프로덕트 job을 배정할 수 있다
    finish_job(db_session, assignments[0][0], JobStatus.DONE)
    again = claim_jobs(db_session)
    assert len(again) == 1


def test_disabled_worker_is_not_used(db_session: Session) -> None:
    product = _product(db_session, "P")
    _worker(db_session, "w1", enabled=False)
    _job(db_session, product.id)
    assert claim_jobs(db_session) == []


def test_finish_job_is_noop_on_terminal_job(db_session: Session) -> None:
    """워치독 회수 후 뒤늦게 도착한 워커의 종료 처리가 상태·락을 건드리지 않는다."""
    product = _product(db_session, "P")
    _worker(db_session, "w1")
    job1 = _job(db_session, product.id)
    assert [jid for jid, _ in claim_jobs(db_session)] == [job1.id]

    # 워치독이 J1을 FAILED로 회수(락 해제·워커 idle)한 상황 모사
    finish_job(db_session, job1.id, JobStatus.FAILED, error="watchdog")
    # 같은 프로덕트의 J2가 새로 배정되어 새 락을 소유한다
    job2 = _job(db_session, product.id)
    assert [jid for jid, _ in claim_jobs(db_session)] == [job2.id]

    # J1의 워커 스레드가 뒤늦게 완료를 보고해도 no-op이어야 한다
    finish_job(db_session, job1.id, JobStatus.DONE, result_summary="late finish")
    db_session.expire_all()
    assert db_session.get(Job, job1.id).status == JobStatus.FAILED.value  # 안 뒤집힘
    assert db_session.get(Job, job1.id).result_summary is None
    assert db_session.get(ProductLock, product.id) is not None  # J2의 락 보존

    # 락이 살아 있으므로 같은 프로덕트의 J3는 동시 배정되지 않는다(배타 불변식 유지)
    _worker(db_session, "w2")
    _job(db_session, product.id)
    assert claim_jobs(db_session) == []


def test_release_lock_requires_ownership(db_session: Session) -> None:
    from genut_service.scheduler.lock import release_lock

    product = _product(db_session, "P")
    worker = _worker(db_session, "w1")
    owner = _job(db_session, product.id)
    other = _job(db_session, product.id)
    db_session.add(
        ProductLock(product_id=product.id, job_id=owner.id, genut_instance_id=worker.id)
    )
    db_session.commit()

    # 소유자가 아닌 job_id로는 해제되지 않는다
    release_lock(db_session, product.id, job_id=other.id)
    db_session.commit()
    assert db_session.get(ProductLock, product.id) is not None

    # 소유자 job_id로는 해제된다
    release_lock(db_session, product.id, job_id=owner.id)
    db_session.commit()
    assert db_session.get(ProductLock, product.id) is None


def test_prep_jobs_are_not_claimed_by_workers(db_session: Session) -> None:
    # 준비(auto_scan/auto_diff) job은 워커 배정 대상이 아니다 — 스케줄러 auto 단계가 실행한다
    product = _product(db_session, "P")
    _worker(db_session, "w1")
    for kind in (JobKind.AUTO_SCAN, JobKind.AUTO_DIFF):
        db_session.add(Job(product_id=product.id, kind=kind.value))
    db_session.commit()

    assert claim_jobs(db_session) == []
    # GENUT job은 여전히 배정된다
    genut_job = _job(db_session, product.id)
    assignments = claim_jobs(db_session)
    assert [jid for jid, _ in assignments] == [genut_job.id]
