"""job 개별 삭제(DELETE /api/jobs/{id}) 테스트.

종결(terminal) job만 삭제 가능하며, 이벤트(DB)와 워크스페이스 로그 파일까지
영구 삭제된다. 실행 중/대기 중 job은 409.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.db.models import Job, JobEvent, Product


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path: Path) -> Iterator[None]:
    """job 로그 경로를 임시 폴더로 격리 — 실제 _workspaces의 개발 잔재와 충돌 방지."""
    settings = get_settings()
    original = settings.workspace_root
    settings.workspace_root = str(tmp_path / "ws")
    yield
    settings.workspace_root = original


def _make_product(db_session: Session) -> Product:
    product = Product(
        name="del-demo",
        product_code="D-1",
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
    )
    db_session.add(product)
    db_session.flush()
    return product


def _make_job(db_session: Session, product: Product, status: str) -> Job:
    job = Job(product_id=product.id, status=status)
    db_session.add(job)
    db_session.flush()
    db_session.add(JobEvent(job_id=job.id, level="info", phase="run", message="line"))
    db_session.commit()
    return job


def test_delete_done_job_removes_events_and_log_file(
    client: TestClient, db_session: Session
) -> None:
    product = _make_product(db_session)
    job = _make_job(db_session, product, "done")
    # 워크스페이스 로그 파일을 만들어 두고 함께 지워지는지 확인한다
    log_path = workspace.job_log_path(job.id)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("[run] line\n", encoding="utf-8")

    resp = client.delete(f"/api/jobs/{job.id}")
    assert resp.status_code == 204

    assert client.get(f"/api/jobs/{job.id}").status_code == 404
    assert db_session.scalars(select(JobEvent).where(JobEvent.job_id == job.id)).first() is None
    assert not log_path.parent.exists()


def test_delete_rejects_inflight_jobs(client: TestClient, db_session: Session) -> None:
    product = _make_product(db_session)
    running = _make_job(db_session, product, "running")
    queued = _make_job(db_session, product, "queued")

    for job in (running, queued):
        resp = client.delete(f"/api/jobs/{job.id}")
        assert resp.status_code == 409, resp.text
        assert "완료된 job만" in resp.json()["detail"]
        assert client.get(f"/api/jobs/{job.id}").status_code == 200  # 그대로 남아 있다


def test_delete_missing_job_returns_404(client: TestClient) -> None:
    assert client.delete("/api/jobs/999999").status_code == 404


def test_delete_each_terminal_status(client: TestClient, db_session: Session) -> None:
    product = _make_product(db_session)
    for status in ("done", "failed", "canceled", "interrupted"):
        job = _make_job(db_session, product, status)
        assert client.delete(f"/api/jobs/{job.id}").status_code == 204, status
