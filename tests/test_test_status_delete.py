"""테스트 현황 삭제 API(개별 파일 / 대상 파일 단위 일괄) 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import Product, TestStatusSnapshot


def _make_product(
    db_session: Session, tmp_path: Path, *, code: str, name: str = "status-demo"
) -> tuple[Product, Path]:
    """out/_Fail/_debug_log 구조를 가진 체크아웃 + 프로덕트를 만든다."""
    root = tmp_path / f"checkout-{code}"
    (root / ".git").mkdir(parents=True)  # existing_product_checkout이 요구하는 체크아웃 표식
    out = root / "tests" / "generated" / "aaa"
    fail = root / "tests" / "generated_Fail" / "aaa"
    log = root / "tests" / "generated_debug_log" / "aaa"
    for d in (out, fail, log):
        d.mkdir(parents=True)
    (out / "aaa_Test.cpp").write_text("// ok", encoding="utf-8")
    (out / "aaa_extra_test.cpp").write_text("// ok2", encoding="utf-8")
    (fail / "aaa_bad_Test.cpp").write_text("// fail", encoding="utf-8")
    (log / "aaa_test.log").write_text("log", encoding="utf-8")
    product = Product(
        name=name,
        product_code=code,
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
        code_path=str(root),
    )
    db_session.add(product)
    db_session.commit()
    return product, root


def test_delete_single_test_file_with_its_log(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """개별 테스트 파일 삭제 — 대응 debug 로그도 함께 지우고 204."""
    _, root = _make_product(db_session, tmp_path, code="S-1")

    resp = client.delete(
        "/api/test-status/file",
        params={"code": "S-1", "path": "tests/generated/aaa/aaa_Test.cpp"},
    )
    assert resp.status_code == 204, resp.text
    assert not (root / "tests/generated/aaa/aaa_Test.cpp").exists()
    # 대소문자 무시 매칭으로 대응 로그(aaa_test.log)도 삭제됐다
    assert not (root / "tests/generated_debug_log/aaa/aaa_test.log").exists()
    # 다른 테스트 파일·실패 파일은 그대로
    assert (root / "tests/generated/aaa/aaa_extra_test.cpp").is_file()
    assert (root / "tests/generated_Fail/aaa/aaa_bad_Test.cpp").is_file()


def test_delete_failed_test_file(client: TestClient, db_session: Session, tmp_path: Path) -> None:
    _, root = _make_product(db_session, tmp_path, code="S-2")
    resp = client.delete(
        "/api/test-status/file",
        params={"code": "S-2", "path": "tests/generated_Fail/aaa/aaa_bad_Test.cpp"},
    )
    assert resp.status_code == 204, resp.text
    assert not (root / "tests/generated_Fail/aaa").exists()  # 비면 stem 폴더 정리


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("../outside.txt", 400),               # 경로 탈출
        ("src/mod.cpp", 404),                  # 허용 루트 밖
        ("tests/generated/aaa/none.cpp", 404),  # 미존재 파일
    ],
)
def test_delete_file_rejects_bad_paths(
    client: TestClient, db_session: Session, tmp_path: Path, path: str, expected: int
) -> None:
    _, root = _make_product(db_session, tmp_path, code="S-3")
    (root / "src").mkdir()
    (root / "src" / "mod.cpp").write_text("// src", encoding="utf-8")

    resp = client.delete("/api/test-status/file", params={"code": "S-3", "path": path})
    assert resp.status_code == expected, resp.text
    assert (root / "src" / "mod.cpp").is_file()  # 허용 루트 밖은 절대 삭제되지 않는다


def test_delete_file_unknown_product_404(client: TestClient) -> None:
    resp = client.delete(
        "/api/test-status/file", params={"code": "NOPE", "path": "tests/generated/a/a_test.c"}
    )
    assert resp.status_code == 404


def test_delete_target_removes_group_folders_across_products(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """대상 파일 단위 일괄 삭제 — 동명 프로덕트 전체에서 성공·실패·로그 폴더 제거."""
    _, root_a = _make_product(db_session, tmp_path, code="G-1", name="grouped")
    _, root_b = _make_product(db_session, tmp_path, code="G-2", name="grouped")

    resp = client.delete(
        "/api/test-status/target",
        params={"project": "Ulysses", "name": "grouped", "path": "src/aaa.c"},
    )
    assert resp.status_code == 200, resp.text
    # 프로덕트당 성공 2 + 실패 1 = 3, 두 프로덕트 합산 6
    assert resp.json() == {"deleted_files": 6}
    for root in (root_a, root_b):
        assert not (root / "tests/generated/aaa").exists()
        assert not (root / "tests/generated_Fail/aaa").exists()
        assert not (root / "tests/generated_debug_log/aaa").exists()


def test_delete_target_conflicts_while_job_running(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    from genut_service.db.models import GenutInstance, Job, ProductLock

    product, root = _make_product(db_session, tmp_path, code="B-1", name="busy-status")
    worker = GenutInstance(
        name="w", repo_url="u", ds_assist_credential_key="k", ds_assist_send_system_name="s"
    )
    db_session.add(worker)
    db_session.flush()
    job = Job(product_id=product.id, status="running")
    db_session.add(job)
    db_session.flush()
    db_session.add(ProductLock(product_id=product.id, job_id=job.id, genut_instance_id=worker.id))
    db_session.commit()

    resp = client.delete(
        "/api/test-status/target",
        params={"project": "Ulysses", "name": "busy-status", "path": "src/aaa.c"},
    )
    assert resp.status_code == 409
    assert (root / "tests/generated/aaa/aaa_Test.cpp").is_file()  # 아무것도 안 지워짐

    resp2 = client.delete(
        "/api/test-status/file",
        params={"code": "B-1", "path": "tests/generated/aaa/aaa_Test.cpp"},
    )
    assert resp2.status_code == 409


def test_delete_invalidates_snapshot(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    """삭제 후 (project, name) 스냅샷이 무효화되어 화면이 즉시 최신을 본다."""
    _make_product(db_session, tmp_path, code="SNAP-1", name="snappy")
    db_session.add(
        TestStatusSnapshot(
            project="Ulysses", name="snappy", fingerprint="f", summary={}, detail=[]
        )
    )
    db_session.commit()

    resp = client.delete(
        "/api/test-status/target",
        params={"project": "Ulysses", "name": "snappy", "path": "src/aaa.c"},
    )
    assert resp.status_code == 200, resp.text
    remaining = db_session.scalars(
        select(TestStatusSnapshot).where(TestStatusSnapshot.name == "snappy")
    ).first()
    assert remaining is None


def test_status_server_does_not_expose_delete(db_session: Session, tmp_path: Path) -> None:
    """읽기 전용 독립 현황 서버(serve-status)에는 삭제 API가 없다(405)."""
    from genut_service.status_main import create_status_app

    app = create_status_app()
    with TestClient(app) as status_client:
        resp = status_client.delete(
            "/api/test-status/file", params={"code": "S-1", "path": "x"}
        )
        assert resp.status_code == 405  # GET /file 라우트만 있어 DELETE는 Method Not Allowed
