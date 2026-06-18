"""M4: 요청 제출(Job) API 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import JobEvent


def _build_checkout(base: Path) -> Path:
    root = base / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "build").mkdir(parents=True)
    for name in ("a.cpp", "b.cpp"):
        (root / "src" / name).write_text("// code\n", encoding="utf-8")
    compdb = [
        {"directory": str(root / "build"), "command": "c++ -c", "file": str(root / "src" / "a.cpp")},
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    return root


def _create_product(client: TestClient, name: str = "demo") -> int:
    payload = {
        "name": name,
        "product_code": "P-1",
        "git_url": "https://example.com/repo.git",
        "compile_db_rel": "build",
        "out_tests_rel": "tests/generated",
        "cmake_configure_cmd": "cmake -S . -B build",
        "cmake_build_cmd": "cmake --build build",
        "test_run_cmd": "ctest --test-dir build",
        "test_generation_mode": "cpp",
    }
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _build_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    return root


def test_submit_splits_included_excluded(client: TestClient, checkout: Path) -> None:
    product_id = _create_product(client)
    resp = client.post(
        "/api/jobs",
        json={"product_id": product_id, "files": ["src/a.cpp", "src/b.cpp"], "function_name": "foo"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["file_list"] == ["src/a.cpp"]
    assert body["excluded_files"] == ["src/b.cpp"]
    assert body["function_name"] == "foo"


def test_submit_missing_product_404(client: TestClient, checkout: Path) -> None:
    resp = client.post("/api/jobs", json={"product_id": 9999, "files": ["x"]})
    assert resp.status_code == 404


def test_list_jobs_filter_and_paginate(client: TestClient, checkout: Path) -> None:
    product_id = _create_product(client)
    for _ in range(3):
        client.post("/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]})
    resp = client.get("/api/jobs", params={"status": "queued", "page": 1, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_get_missing_job_404(client: TestClient) -> None:
    assert client.get("/api/jobs/9999").status_code == 404


def test_cancel_missing_job_404(client: TestClient) -> None:
    assert client.post("/api/jobs/99999/cancel").status_code == 404


def test_cancel_non_running_job_409(client: TestClient, checkout: Path) -> None:
    product_id = _create_product(client)
    job_id = client.post(
        "/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]}
    ).json()["id"]
    # queued(실행 중 아님) → 409
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_cancel_running_job_marks_for_cancellation(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    from genut_service.db.models import Job
    from genut_service.enums import JobStatus
    from genut_service.runner import process_registry

    product_id = _create_product(client)
    job_id = client.post(
        "/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]}
    ).json()["id"]
    # running 상태로 만든 뒤 강제 종료 요청
    job = db_session.get(Job, job_id)
    job.status = JobStatus.RUNNING.value
    db_session.commit()
    try:
        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 200
        assert process_registry.is_canceled(job_id) is True
    finally:
        process_registry.unregister(job_id)


def test_rerun_creates_new_queued_job(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    from genut_service.db.models import Job
    from genut_service.enums import JobStatus

    product_id = _create_product(client)
    original = client.post(
        "/api/jobs",
        json={"product_id": product_id, "files": ["src/a.cpp", "src/b.cpp"], "function_name": "foo"},
    ).json()
    # terminal(done) 상태로 만든다
    job = db_session.get(Job, original["id"])
    job.status = JobStatus.DONE.value
    db_session.commit()

    resp = client.post(f"/api/jobs/{original['id']}/rerun")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] != original["id"]
    assert body["status"] == "queued"
    # 입력은 그대로 복사된다
    assert body["file_list"] == original["file_list"] == ["src/a.cpp"]
    assert body["excluded_files"] == original["excluded_files"] == ["src/b.cpp"]
    assert body["function_name"] == "foo"
    # 워커/시작시각은 복사하지 않아 스케줄러가 재배정한다
    assert body["genut_instance_id"] is None
    assert body["started_at"] is None


def test_rerun_missing_job_404(client: TestClient) -> None:
    assert client.post("/api/jobs/99999/rerun").status_code == 404


def test_rerun_non_terminal_409(client: TestClient, checkout: Path) -> None:
    product_id = _create_product(client)
    job_id = client.post(
        "/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]}
    ).json()["id"]
    # 갓 제출한 queued(미완료) job → 재수행 불가 409
    assert client.post(f"/api/jobs/{job_id}/rerun").status_code == 409


def test_job_logs_with_since(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    product_id = _create_product(client)
    job_id = client.post("/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]}).json()["id"]

    db_session.add_all(
        [
            JobEvent(job_id=job_id, message="first", phase="schedule"),
            JobEvent(job_id=job_id, message="second", phase="run"),
        ]
    )
    db_session.commit()

    logs = client.get(f"/api/jobs/{job_id}/logs").json()
    assert [e["message"] for e in logs] == ["first", "second"]

    first_id = logs[0]["id"]
    after = client.get(f"/api/jobs/{job_id}/logs", params={"since": first_id}).json()
    assert [e["message"] for e in after] == ["second"]
