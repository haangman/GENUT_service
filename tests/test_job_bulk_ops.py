"""프로덕트 단위 job 일괄 중지(cancel-all)·종결 job 일괄 삭제(finished) 테스트."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, JobEvent, Product, ProductLock
from genut_service.runner import process_registry
from genut_service.scheduler.engine import claim_jobs


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path: Path) -> Iterator[None]:
    settings = get_settings()
    original = settings.workspace_root
    settings.workspace_root = str(tmp_path / "ws")
    yield
    settings.workspace_root = original


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    yield
    # 테스트가 남긴 취소 플래그가 다른 테스트로 새지 않게 정리
    for job_id in range(1, 50):
        process_registry.unregister(job_id)


def _make_product(db_session: Session, name: str = "bulk-demo") -> Product:
    product = Product(
        name=name,
        product_code=f"{name}-code",
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
    )
    db_session.add(product)
    db_session.flush()
    return product


def _job(db_session: Session, product: Product, status: str, kind: str = "genut") -> Job:
    job = Job(product_id=product.id, status=status, kind=kind)
    db_session.add(job)
    db_session.flush()
    return job


def test_cancel_all_cancels_queued_and_flags_running(
    client: TestClient, db_session: Session
) -> None:
    product = _make_product(db_session)
    q1 = _job(db_session, product, "queued")
    q2 = _job(db_session, product, "queued", kind="auto_scan")  # 준비 job도 대상
    running = _job(db_session, product, "running")
    worker = GenutInstance(
        name="w", repo_url="u", ds_assist_credential_key="k",
        ds_assist_send_system_name="s", worker_status="busy",
    )
    db_session.add(worker)
    db_session.flush()
    db_session.add(ProductLock(product_id=product.id, job_id=running.id, genut_instance_id=worker.id))
    db_session.commit()

    resp = client.post(f"/api/products/{product.id}/jobs/cancel-all")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"canceled_queued": 2, "canceling_running": 1}

    db_session.expire_all()
    # 대기 job은 즉시 canceled 확정(+오류 사유·finished_at)
    for job in (q1, q2):
        row = db_session.get(Job, job.id)
        assert row.status == "canceled"
        assert row.finished_at is not None
        assert "일괄" in (row.error or "")
    # 실행 중 job은 워커가 확정하도록 취소 플래그만 세워진다(상태·락은 그대로)
    assert db_session.get(Job, running.id).status == "running"
    assert process_registry.is_canceled(running.id)
    assert db_session.get(ProductLock, product.id) is not None


def test_cancel_all_leaves_other_products_untouched(
    client: TestClient, db_session: Session
) -> None:
    target = _make_product(db_session, "bulk-a")
    other = _make_product(db_session, "bulk-b")
    _job(db_session, target, "queued")
    other_q = _job(db_session, other, "queued")
    db_session.commit()

    resp = client.post(f"/api/products/{target.id}/jobs/cancel-all")
    assert resp.json()["canceled_queued"] == 1
    db_session.expire_all()
    assert db_session.get(Job, other_q.id).status == "queued"


def test_canceled_queued_jobs_are_not_claimed(client: TestClient, db_session: Session) -> None:
    """일괄 취소된 대기 job은 이후 스케줄러 claim에 집히지 않는다."""
    product = _make_product(db_session)
    _job(db_session, product, "queued")
    worker = GenutInstance(
        name="idle-w", repo_url="u", ds_assist_credential_key="k",
        ds_assist_send_system_name="s", worker_status="idle", enabled=True,
    )
    db_session.add(worker)
    db_session.commit()

    client.post(f"/api/products/{product.id}/jobs/cancel-all")
    assigned = claim_jobs(db_session)
    assert assigned == []


def test_cancel_all_unknown_product_404(client: TestClient) -> None:
    assert client.post("/api/products/999999/jobs/cancel-all").status_code == 404


def test_delete_finished_removes_terminal_jobs_only(
    client: TestClient, db_session: Session
) -> None:
    product = _make_product(db_session)
    terminal_ids = []
    for status in ("done", "failed", "canceled", "interrupted"):
        job = _job(db_session, product, status)
        db_session.add(JobEvent(job_id=job.id, level="info", phase="run", message="x"))
        terminal_ids.append(job.id)
    queued = _job(db_session, product, "queued")
    running = _job(db_session, product, "running")
    db_session.commit()
    # 종결 job 하나의 로그 폴더도 함께 지워지는지
    log_path = workspace.job_log_path(terminal_ids[0])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("log", encoding="utf-8")

    resp = client.delete(f"/api/products/{product.id}/jobs/finished")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"deleted": 4}

    db_session.expire_all()
    for job_id in terminal_ids:
        assert db_session.get(Job, job_id) is None
        assert (
            db_session.scalars(select(JobEvent).where(JobEvent.job_id == job_id)).first()
            is None
        )
    assert not log_path.parent.exists()
    # 미종결 job은 남는다
    assert db_session.get(Job, queued.id) is not None
    assert db_session.get(Job, running.id) is not None


def test_delete_finished_unknown_product_404(client: TestClient) -> None:
    assert client.delete("/api/products/999999/jobs/finished").status_code == 404
