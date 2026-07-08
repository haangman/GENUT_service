"""M2: 프로덕트 등록 API 테스트."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _payload(name: str = "demo", **overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


def test_create_and_get_product(client: TestClient) -> None:
    payload = _payload(
        patches=[
            {"name": "second", "content": "diff-2", "order_index": 1},
            {"name": "first", "content": "diff-1", "order_index": 0},
        ]
    )
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["id"] > 0
    assert created["test_generation_mode"] == "cpp"
    assert [p["order_index"] for p in created["patches"]] == [0, 1]

    got = client.get(f"/api/products/{created['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "demo"


def test_paths_are_normalized(client: TestClient) -> None:
    resp = client.post(
        "/api/products", json=_payload(compile_db_rel="build\\out\\", out_tests_rel="/tests/gen")
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["compile_db_rel"] == "build/out"
    assert body["out_tests_rel"] == "tests/gen"


def test_parent_path_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/products", json=_payload(compile_db_rel="../secret"))
    assert resp.status_code == 422


def test_duplicate_name_allowed_with_different_id(client: TestClient) -> None:
    # 같은 이름이라도 서로 다른 id(다른 정보)로 등록할 수 있다
    a = client.post("/api/products", json=_payload("dup", product_code="P-A"))
    b = client.post("/api/products", json=_payload("dup", product_code="P-B"))
    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text
    assert a.json()["id"] != b.json()["id"]
    assert a.json()["name"] == b.json()["name"] == "dup"


def test_list_pagination(client: TestClient) -> None:
    for i in range(3):
        client.post("/api/products", json=_payload(f"p{i}"))
    resp = client.get("/api/products", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_update_product_and_patches(client: TestClient) -> None:
    created = client.post("/api/products", json=_payload()).json()
    resp = client.put(
        f"/api/products/{created['id']}",
        json={"git_ref": "develop", "patches": [{"name": "p", "content": "d", "order_index": 0}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_ref"] == "develop"
    assert len(body["patches"]) == 1


def test_delete_product(client: TestClient) -> None:
    created = client.post("/api/products", json=_payload()).json()
    assert client.delete(f"/api/products/{created['id']}").status_code == 204
    assert client.get(f"/api/products/{created['id']}").status_code == 404


def test_delete_product_removes_finished_job_history(client, db_session) -> None:
    """종료된 job 이력이 있어도 삭제된다(이력·이벤트 동반 삭제) — FK로 500 나던 회귀 방지."""
    from sqlalchemy import select

    from genut_service.db.models import Job, JobEvent

    pid = client.post("/api/products", json=_payload("with-history")).json()["id"]
    job = Job(product_id=pid, status="done")
    db_session.add(job)
    db_session.flush()
    db_session.add(JobEvent(job_id=job.id, message="m"))
    db_session.commit()

    assert client.delete(f"/api/products/{pid}").status_code == 204
    db_session.expire_all()
    assert db_session.scalars(select(Job).where(Job.product_id == pid)).all() == []
    assert db_session.scalars(select(JobEvent)).all() == []


def test_delete_product_with_active_job_conflicts(client, db_session) -> None:
    """대기/실행 중 job이 있으면 409로 거부하고 프로덕트는 남는다."""
    from genut_service.db.models import Job

    pid = client.post("/api/products", json=_payload("busy")).json()["id"]
    db_session.add(Job(product_id=pid, status="running"))
    db_session.commit()

    resp = client.delete(f"/api/products/{pid}")
    assert resp.status_code == 409
    assert "삭제할 수 없다" in resp.json()["detail"]
    assert client.get(f"/api/products/{pid}").status_code == 200


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/api/products/9999").status_code == 404


def test_code_path_normalized_and_optional(client: TestClient) -> None:
    # 절대경로(백슬래시) → 슬래시 정규화 후 그대로 유지
    abs_body = client.post("/api/products", json=_payload("cp-abs", code_path="C:\\repos\\foo")).json()
    assert abs_body["code_path"] == "C:/repos/foo"
    # 상대경로 정규화
    rel_body = client.post("/api/products", json=_payload("cp-rel", code_path="repos/./foo")).json()
    assert rel_body["code_path"] == "repos/foo"
    # 빈 값/미지정 → None
    assert client.post("/api/products", json=_payload("cp-empty", code_path="")).json()["code_path"] is None
    assert client.post("/api/products", json=_payload("cp-none")).json()["code_path"] is None


def test_code_path_rejects_parent(client: TestClient) -> None:
    assert client.post("/api/products", json=_payload("cp-bad", code_path="../etc")).status_code == 422


# --- 자동 실행 모드: 대상 파일 미리보기 + auto 필드 -----------------------


def _make_compile_db(root: Path, rels: list[str]) -> None:
    (root / "build").mkdir(parents=True, exist_ok=True)
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("//", encoding="utf-8")
    compdb = [
        {"directory": str(root / "build"), "command": "cc -c", "file": str(root / rel)}
        for rel in rels
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")


def test_preview_target_files_default_filter_and_pattern_flags(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "code"
    root.mkdir()
    _make_compile_db(root, ["src/calc.c", "src/util.c", "build/gen.c", "tests/foo.c"])
    resp = client.post(
        "/api/products/target-files",
        json={"code_path": str(root), "compile_db_rel": "build", "exclude_globs": ["*util*"]},
    )
    assert resp.status_code == 200, resp.text
    by_path = {f["path"]: f["excluded_by_pattern"] for f in resp.json()["files"]}
    # build/gen.c(build 폴더)·tests/foo.c(test 폴더)는 기본 필터로 제외, 나머지만 후보
    assert set(by_path) == {"src/calc.c", "src/util.c"}
    assert by_path["src/util.c"] is True  # *util* 패턴 매칭
    assert by_path["src/calc.c"] is False


def test_preview_target_files_empty_when_blank(client: TestClient) -> None:
    resp = client.post(
        "/api/products/target-files",
        json={"code_path": "", "compile_db_rel": "", "exclude_globs": []},
    )
    assert resp.status_code == 200
    assert resp.json()["files"] == []


def test_product_read_has_auto_defaults(client: TestClient) -> None:
    created = client.post("/api/products", json=_payload("auto-defaults")).json()
    assert created["auto_run"] is False
    assert created["auto_interval_seconds"] is None
    assert created["auto_file_list"] == []
    assert created["cmake_template"] is None


def _make_auto_run_product(db_session, name: str = "auto-now", auto_run: bool = True):
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
        auto_interval_seconds=3600 if auto_run else None,
        auto_file_list=["src/aaa.c"] if auto_run else [],
    )
    db_session.add(product)
    db_session.commit()
    return product


def test_run_auto_now_queues_cycle_pair(client, db_session) -> None:
    """수동 실행: 주기와 무관하게 diff→scan 준비 job 쌍을 즉시 큐잉한다."""
    from datetime import datetime, timezone

    product = _make_auto_run_product(db_session)
    product.last_auto_run_at = datetime.now(timezone.utc)  # 주기상 한참 남은 상태
    db_session.commit()

    resp = client.post(f"/api/products/{product.id}/auto/run")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert [job["kind"] for job in body] == ["auto_diff", "auto_scan"]
    assert all(job["origin"] == "auto" for job in body)
    assert all(job["status"] == "queued" for job in body)

    # 이전 사이클이 비종료인 동안 재실행 → 409 (중복 사이클 방지)
    assert client.post(f"/api/products/{product.id}/auto/run").status_code == 409


def test_run_auto_now_rejects_non_auto_and_missing(client, db_session) -> None:
    plain = _make_auto_run_product(db_session, name="plain-now", auto_run=False)
    assert client.post(f"/api/products/{plain.id}/auto/run").status_code == 409
    assert client.post("/api/products/999999/auto/run").status_code == 404
