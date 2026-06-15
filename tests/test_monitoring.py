"""M9: 워커/큐 모니터링 + stale-lock janitor 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import JobStatus, WorkerStatus
from genut_service.scheduler.engine import claim_jobs
from genut_service.scheduler.janitor import release_stale_locks


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
