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
    assert body["kind"] == "genut"
    assert body["origin"] == "manual"
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


def test_list_jobs_filters_by_origin_and_kind(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    from genut_service.db.models import Job
    from genut_service.enums import JobKind, JobOrigin

    product_id = _create_product(client)
    client.post("/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]})  # manual
    db_session.add_all(
        [
            Job(
                product_id=product_id,
                kind=JobKind.GENUT.value,
                origin=JobOrigin.AUTO.value,
                file_list=["src/a.cpp"],
            ),
            Job(
                product_id=product_id,
                kind=JobKind.AUTO_SCAN.value,
                origin=JobOrigin.AUTO.value,
            ),
        ]
    )
    db_session.commit()

    manual = client.get("/api/jobs", params={"origin": "manual"}).json()
    assert manual["total"] == 1
    assert manual["items"][0]["origin"] == "manual"

    auto = client.get("/api/jobs", params={"origin": "auto"}).json()
    assert auto["total"] == 2

    scans = client.get("/api/jobs", params={"kind": "auto_scan"}).json()
    assert scans["total"] == 1
    assert scans["items"][0]["kind"] == "auto_scan"


def _make_auto_product(db_session: Session, name: str, auto_run: bool = True):
    from genut_service.db.models import Product

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
        auto_run=auto_run,
        auto_interval_seconds=120 if auto_run else None,
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_auto_history_groups_recent_jobs_per_product(
    client: TestClient, db_session: Session
) -> None:
    from genut_service.db.models import Job
    from genut_service.enums import JobKind, JobOrigin

    busy = _make_auto_product(db_session, "auto-busy")
    idle = _make_auto_product(db_session, "auto-idle")
    plain = _make_auto_product(db_session, "plain", auto_run=False)

    # busy: auto job 5개 + manual 1개(제외 대상). plain: auto job 1개(그룹 자체가 제외).
    for i in range(5):
        db_session.add(
            Job(
                product_id=busy.id,
                kind=JobKind.GENUT.value if i % 2 == 0 else JobKind.AUTO_SCAN.value,
                origin=JobOrigin.AUTO.value,
            )
        )
    db_session.add(Job(product_id=busy.id, origin=JobOrigin.MANUAL.value))
    db_session.add(Job(product_id=plain.id, origin=JobOrigin.AUTO.value))
    db_session.commit()

    resp = client.get("/api/jobs/auto-history", params={"per_product": 3})
    assert resp.status_code == 200, resp.text
    groups = resp.json()

    assert [g["product_name"] for g in groups] == ["auto-busy", "auto-idle"]
    busy_group = groups[0]
    assert busy_group["product_code"] == "auto-busy"
    assert busy_group["auto_interval_seconds"] == 120
    assert busy_group["total"] == 5  # manual job은 세지 않는다
    assert len(busy_group["jobs"]) == 3  # 최근 3개만
    ids = [j["id"] for j in busy_group["jobs"]]
    assert ids == sorted(ids, reverse=True)  # 최신(id 내림차순)
    assert all(j["origin"] == "auto" for j in busy_group["jobs"])

    idle_group = groups[1]
    assert idle_group["total"] == 0
    assert idle_group["jobs"] == []  # 이력 없는 auto 프로덕트도 빈 그룹으로 노출


def test_auto_history_empty_without_auto_products(client: TestClient) -> None:
    resp = client.get("/api/jobs/auto-history")
    assert resp.status_code == 200
    assert resp.json() == []


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
    assert body["kind"] == "genut"
    assert body["origin"] == "manual"
    # 워커/시작시각은 복사하지 않아 스케줄러가 재배정한다
    assert body["genut_instance_id"] is None
    assert body["started_at"] is None


def test_rerun_copies_kind_and_origin_for_prep_job(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    """준비(prep) job의 재수행은 kind/origin을 유지한 새 queued job이 된다."""
    from genut_service.db.models import Job
    from genut_service.enums import JobKind, JobOrigin, JobStatus

    product_id = _create_product(client)
    prep = Job(
        product_id=product_id,
        kind=JobKind.AUTO_SCAN.value,
        origin=JobOrigin.AUTO.value,
        status=JobStatus.DONE.value,
    )
    db_session.add(prep)
    db_session.commit()

    resp = client.post(f"/api/jobs/{prep.id}/rerun")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] != prep.id
    assert body["status"] == "queued"
    assert body["kind"] == "auto_scan"
    assert body["origin"] == "auto"


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


def test_jobread_serializes_naive_datetime_as_utc() -> None:
    """naive datetime은 UTC로 간주해 tz 인식(+00:00) ISO로 직렬화한다. None은 그대로."""
    from datetime import datetime

    from genut_service.schemas.job import JobRead

    model = JobRead(
        id=1,
        product_id=1,
        genut_instance_id=None,
        status="running",
        kind="genut",
        origin="manual",
        function_name=None,
        file_list=[],
        excluded_files=[],
        attempt=0,
        submitted_at=datetime(2026, 6, 23, 7, 0, 0),
        started_at=datetime(2026, 6, 23, 7, 41, 20, 938327),
        finished_at=None,
        result_summary=None,
        error=None,
    )
    dumped = model.model_dump(mode="json")
    assert dumped["submitted_at"] == "2026-06-23T07:00:00+00:00"
    assert dumped["started_at"] == "2026-06-23T07:41:20.938327+00:00"
    assert dumped["finished_at"] is None


def test_job_api_datetimes_are_tz_aware(
    client: TestClient, checkout: Path, db_session: Session
) -> None:
    """GET /jobs/{id}의 datetime은 tz 인식으로 나와 클라가 로컬로 오해하지 않는다."""
    from datetime import datetime, timezone

    from genut_service.db.models import Job
    from genut_service.enums import JobStatus

    product_id = _create_product(client)
    job_id = client.post(
        "/api/jobs", json={"product_id": product_id, "files": ["src/a.cpp"]}
    ).json()["id"]

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["submitted_at"].endswith("+00:00")  # 제출 시각은 tz 인식
    assert body["started_at"] is None

    # 시작 시각을 채우면 그것도 tz 인식으로 직렬화된다(실행 중 경과 계산이 어긋나지 않도록)
    job = db_session.get(Job, job_id)
    job.status = JobStatus.RUNNING.value
    job.started_at = datetime(2026, 6, 23, 7, 41, 20, tzinfo=timezone.utc)
    db_session.commit()
    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["started_at"] == "2026-06-23T07:41:20+00:00"
