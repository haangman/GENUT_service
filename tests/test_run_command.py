"""프로덕트 폼 명령 시험 실행(run-command) API 테스트."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _payload(dest: Path, command: str) -> dict:
    return {"command": command, "code_path": str(dest)}


def test_run_command_returns_output_and_exit_code(
    client: TestClient, tmp_path: Path
) -> None:
    dest = tmp_path / "checkout"
    dest.mkdir()
    resp = client.post("/api/products/run-command", json=_payload(dest, "echo hello"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exit_code"] == 0
    assert "hello" in body["output"]
    assert body["duration_seconds"] >= 0


def test_run_command_runs_in_code_path(client: TestClient, tmp_path: Path) -> None:
    dest = tmp_path / "checkout"
    dest.mkdir()
    cwd_cmd = "cd" if os.name == "nt" else "pwd"
    body = client.post("/api/products/run-command", json=_payload(dest, cwd_cmd)).json()
    assert str(dest.resolve()).lower() in body["output"].lower()


def test_run_command_reports_nonzero_exit_as_result(
    client: TestClient, tmp_path: Path
) -> None:
    """명령 실패는 HTTP 오류가 아니라 exit_code로 전달된다."""
    dest = tmp_path / "checkout"
    dest.mkdir()
    resp = client.post("/api/products/run-command", json=_payload(dest, "exit 3"))
    assert resp.status_code == 200
    assert resp.json()["exit_code"] == 3


def test_run_command_missing_dir_400(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(
        "/api/products/run-command", json=_payload(tmp_path / "nope", "echo x")
    )
    assert resp.status_code == 400
    assert "먼저 다운로드" in resp.json()["detail"]


def test_run_command_conflicts_while_job_running(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    from genut_service.db.models import GenutInstance, Job, Product, ProductLock

    dest = tmp_path / "busy-checkout"
    dest.mkdir()
    product = Product(
        name="busy",
        product_code="B-1",
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
        code_path=str(dest),
    )
    worker = GenutInstance(
        name="w",
        repo_url="u",
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
    )
    db_session.add_all([product, worker])
    db_session.flush()
    job = Job(product_id=product.id, status="running")
    db_session.add(job)
    db_session.flush()
    db_session.add(
        ProductLock(product_id=product.id, job_id=job.id, genut_instance_id=worker.id)
    )
    db_session.commit()

    resp = client.post("/api/products/run-command", json=_payload(dest, "echo x"))
    assert resp.status_code == 409
    assert "실행 중" in resp.json()["detail"]


def test_run_command_requires_command_and_code_path(
    client: TestClient, tmp_path: Path
) -> None:
    dest = tmp_path / "c"
    dest.mkdir()
    assert (
        client.post(
            "/api/products/run-command", json={"command": "  ", "code_path": str(dest)}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/products/run-command", json={"command": "echo x", "code_path": " "}
        ).status_code
        == 422
    )
