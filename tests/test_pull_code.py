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


# 새 파일을 만드는 patch — 등록 폼의 패치가 다운로드에도 적용되는지 검증용
_NEW_FILE_PATCH = """diff --git a/src/patched.txt b/src/patched.txt
new file mode 100644
--- /dev/null
+++ b/src/patched.txt
@@ -0,0 +1 @@
+patched by service
"""

# 첫 패치가 만든 파일을 수정하는 patch — 순서 보장 검증용(첫 패치에 의존)
_APPEND_LINE_PATCH = """diff --git a/src/patched.txt b/src/patched.txt
--- a/src/patched.txt
+++ b/src/patched.txt
@@ -1 +1,2 @@
 patched by service
+second line
"""


def test_pull_code_applies_patches_in_order(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    """폼의 패치가 다운로드(clone) 직후 order_index 순서대로 적용된다."""
    spec = make_virtual_product("pull-patch")
    dest = tmp_path / "checkout"

    resp = client.post(
        "/api/products/pull-code",
        json=_payload(
            spec["git_url"],
            dest,
            patches=[
                {"name": "append-line", "content": _APPEND_LINE_PATCH, "order_index": 1},
                {"name": "new-file", "content": _NEW_FILE_PATCH, "order_index": 0},
            ],
        ),
    )
    assert resp.status_code == 200, resp.text
    # order_index 순서(new-file → append-line)로 적용돼야 두 번째 패치가 성공한다
    assert (dest / "src" / "patched.txt").read_text(encoding="utf-8") == (
        "patched by service\nsecond line\n"
    )
    # 폼 로그창용 log에 패치 적용 내역이 남는다
    body = resp.json()
    assert "patch 적용: new-file" in body["log"]
    assert "patch 적용: append-line" in body["log"]


def test_pull_code_reapplies_patches_on_update(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    """제자리 업데이트(reset --hard) 후에도 패치가 멱등 재적용된다."""
    spec = make_virtual_product("pull-patch-upd")
    repo = Path(spec["repo"])
    dest = tmp_path / "checkout"
    patches = [{"name": "new-file", "content": _NEW_FILE_PATCH, "order_index": 0}]
    assert client.post(
        "/api/products/pull-code", json=_payload(repo, dest, patches=patches)
    ).status_code == 200

    # 원격에 새 커밋 추가 후 재다운로드 — 새 커밋 반영 + 패치 유지
    (repo / "src" / "new.cpp").write_text("// new", encoding="utf-8")
    _git_commit_all(repo)
    second = client.post(
        "/api/products/pull-code", json=_payload(repo, dest, patches=patches)
    )
    assert second.status_code == 200, second.text
    assert second.json()["detail"] == "업데이트 완료"
    assert (dest / "src" / "new.cpp").is_file()
    assert (dest / "src" / "patched.txt").is_file()


def test_pull_code_invalid_patch_returns_400_with_name(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    """패치 적용 실패는 400 + 어느 패치인지 detail에 담는다(코드는 이미 받은 상태)."""
    spec = make_virtual_product("pull-patch-bad")
    dest = tmp_path / "checkout"

    resp = client.post(
        "/api/products/pull-code",
        json=_payload(
            spec["git_url"],
            dest,
            patches=[{"name": "broken", "content": "this is not a diff", "order_index": 0}],
        ),
    )
    assert resp.status_code == 400
    assert "broken" in resp.json()["detail"]
    assert (dest / ".git").is_dir()  # 체크아웃 자체는 완료된 상태


def test_pull_code_skips_blank_patch_content(
    client: TestClient, make_virtual_product, tmp_path: Path
) -> None:
    """빈 내용 패치(폼의 빈 행)는 조용히 건너뛴다."""
    spec = make_virtual_product("pull-patch-blank")
    dest = tmp_path / "checkout"

    resp = client.post(
        "/api/products/pull-code",
        json=_payload(
            spec["git_url"], dest, patches=[{"name": "", "content": "   ", "order_index": 0}]
        ),
    )
    assert resp.status_code == 200, resp.text
    assert "patch 적용" not in resp.json()["log"]


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
