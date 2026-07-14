"""프로덕트 코드 다운로드(pull-code) API 테스트."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def _payload(repo: Path | str, dest: Path, **overrides) -> dict:
    body = {"git_url": str(repo), "git_ref": "main", "code_path": str(dest)}
    body.update(overrides)
    return body


def _git_commit_all(repo: Path, message: str = "update") -> None:
    for args in (["add", "-A"], ["commit", "-m", message]):
        subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )


def test_pull_code_clones_into_new_path(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    spec = make_virtual_product("pull-demo")
    dest = tmp_path / "checkout"

    resp = client.post("/api/products/pull-code", json=_payload(spec["git_url"], dest))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["detail"] == "클론 완료"
    assert (dest / ".git").is_dir()
    assert (dest / "src" / "a.cpp").is_file()
    # 폼 로그창용: 받은 코드의 최근 커밋 정보가 log에 담긴다
    assert "최근 커밋" in body["log"]
    assert "init" in body["log"]


def test_pull_code_updates_existing_checkout_and_keeps_out_dir(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    spec = make_virtual_product("pull-upd")
    repo = Path(spec["repo"])
    dest = tmp_path / "checkout"
    assert client.post(
        "/api/products/pull-code", json=_payload(repo, dest)
    ).json()["detail"] == "클론 완료"

    # 생성 테스트 산출물을 만들어 두고, 원격에 새 커밋을 추가한다
    out_dir = dest / "tests" / "generated"
    out_dir.mkdir(parents=True)
    (out_dir / "foo_Test.cpp").write_text("// t", encoding="utf-8")
    (repo / "src" / "new.cpp").write_text("// new", encoding="utf-8")
    _git_commit_all(repo)

    second = client.post(
        "/api/products/pull-code",
        json=_payload(repo, dest, out_tests_rel="tests/generated"),
    )
    assert second.status_code == 200, second.text
    assert second.json()["detail"] == "업데이트 완료"
    assert (dest / "src" / "new.cpp").is_file()  # 새 커밋 반영(제자리 업데이트)
    assert (out_dir / "foo_Test.cpp").is_file()  # 생성 테스트 보존


def test_pull_code_conflicts_while_job_running(
    client: TestClient, db_session: Session, make_virtual_product, tmp_path: Path
) -> None:
    from genut_service.db.models import GenutInstance, Job, Product, ProductLock

    spec = make_virtual_product("pull-busy")
    dest = tmp_path / "busy-checkout"
    product = Product(
        name="busy",
        product_code="B-1",
        git_url=spec["git_url"],
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

    resp = client.post("/api/products/pull-code", json=_payload(spec["git_url"], dest))
    assert resp.status_code == 409
    assert "실행 중" in resp.json()["detail"]
    assert not dest.exists()  # 거부됐으므로 아무것도 받지 않는다


def test_pull_code_bad_url_returns_400_with_detail(
    client: TestClient, tmp_path: Path
) -> None:
    resp = client.post(
        "/api/products/pull-code",
        json=_payload(tmp_path / "no-such-repo", tmp_path / "dest"),
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]  # git 실패 원인이 담긴다


def test_pull_code_update_with_missing_ref_returns_400(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    """제자리 업데이트의 실패(없는 ref)도 성공으로 오인하지 않는다(strict)."""
    spec = make_virtual_product("pull-strict")
    dest = tmp_path / "checkout"
    assert client.post(
        "/api/products/pull-code", json=_payload(spec["git_url"], dest)
    ).status_code == 200

    resp = client.post(
        "/api/products/pull-code",
        json=_payload(spec["git_url"], dest, git_ref="no-such-branch"),
    )
    assert resp.status_code == 400


def test_pull_code_requires_git_url_and_code_path(client: TestClient) -> None:
    assert (
        client.post(
            "/api/products/pull-code", json={"git_url": "u", "code_path": "   "}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/products/pull-code", json={"git_url": "  ", "code_path": "x"}
        ).status_code
        == 422
    )
