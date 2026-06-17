"""M5: 스케줄러 claim/finish 동시성·배타 불변식 테스트 (결정론적, 스레드 없음)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import JobStatus, WorkerStatus
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
