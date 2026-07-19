"""git_update_mode(reset|rebase) — 영속 체크아웃 갱신 방식 테스트.

rebase 모드는 로컬 전용 커밋(cherry-pick 등)을 원격 최신 위로 유지해야 하고,
충돌 시에는 원상 복구 후 GitError로 표면화해야 한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product
from genut_service.runner import genut_runner, git_ops


def _git(*args: str, cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout.strip()


def _init_origin(tmp_path: Path, content: str = "line-a\n") -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git("-c", "init.defaultBranch=main", "init", cwd=origin)
    _git("config", "user.email", "t@t", cwd=origin)
    _git("config", "user.name", "t", cwd=origin)
    (origin / "mod.c").write_text(content, encoding="utf-8")
    _git("add", "-A", cwd=origin)
    _git("commit", "-m", "init", cwd=origin)
    return origin


def _clone(origin: Path, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", str(origin), str(dest)],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    _git("config", "user.email", "t@t", cwd=dest)
    _git("config", "user.name", "t", cwd=dest)


def _commit_file(repo: Path, rel: str, content: str, message: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-m", message, cwd=repo)


# ---------- git_ops.ensure_checkout 단위 ----------

def test_rebase_keeps_local_commit_and_applies_remote(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(dest, "cherry.c", "int cherry(void);\n", "cherry-pick")
    _commit_file(origin, "remote.c", "int remote(void);\n", "remote change")

    git_ops.ensure_checkout(str(origin), "main", dest, update_mode="rebase")

    assert (dest / "cherry.c").is_file()  # 로컬 커밋 유지
    assert (dest / "remote.c").is_file()  # 원격 최신 반영
    # 로컬 커밋이 원격 tip 위로 rebase됐다(원격 tip이 조상)
    origin_head = _git("rev-parse", "HEAD", cwd=origin)
    _git("merge-base", "--is-ancestor", origin_head, "HEAD", cwd=dest)


def test_rebase_fast_forwards_without_local_commits(tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(origin, "remote.c", "int remote(void);\n", "remote change")

    git_ops.ensure_checkout(str(origin), "main", dest, update_mode="rebase")

    assert _git("rev-parse", "HEAD", cwd=dest) == _git("rev-parse", "HEAD", cwd=origin)


def test_rebase_conflict_raises_and_restores_checkout(tmp_path: Path) -> None:
    """충돌 시 GitError + rebase --abort로 원상 복구(진행 중 rebase 없음)."""
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(dest, "mod.c", "line-local\n", "local change")
    _commit_file(origin, "mod.c", "line-remote\n", "remote change")
    local_tip = _git("rev-parse", "HEAD", cwd=dest)

    with pytest.raises(git_ops.GitError):
        git_ops.ensure_checkout(str(origin), "main", dest, update_mode="rebase")

    assert (dest / "mod.c").read_text(encoding="utf-8") == "line-local\n"
    assert _git("rev-parse", "HEAD", cwd=dest) == local_tip
    assert not (dest / ".git" / "rebase-merge").exists()
    assert not (dest / ".git" / "rebase-apply").exists()


def test_default_reset_drops_local_commit(tmp_path: Path) -> None:
    """기본(reset)은 기존대로 로컬 커밋을 버리고 원격에 강제 일치한다(회귀 가드)."""
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(dest, "cherry.c", "int cherry(void);\n", "cherry-pick")
    _commit_file(origin, "remote.c", "int remote(void);\n", "remote change")

    git_ops.ensure_checkout(str(origin), "main", dest)

    assert not (dest / "cherry.c").exists()
    assert (dest / "remote.c").is_file()


# ---------- pull-code API ----------

def test_pull_code_rebase_mode_keeps_local_commit(
    client: TestClient, tmp_path: Path
) -> None:
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(dest, "cherry.c", "int cherry(void);\n", "cherry-pick")
    _commit_file(origin, "remote.c", "int remote(void);\n", "remote change")

    resp = client.post(
        "/api/products/pull-code",
        json={
            "git_url": str(origin),
            "git_ref": "main",
            "code_path": str(dest),
            "git_update_mode": "rebase",
        },
    )
    assert resp.status_code == 200, resp.text
    assert (dest / "cherry.c").is_file()
    assert (dest / "remote.c").is_file()


def test_pull_code_rebase_conflict_returns_400(client: TestClient, tmp_path: Path) -> None:
    origin = _init_origin(tmp_path)
    dest = tmp_path / "checkout"
    _clone(origin, dest)
    _commit_file(dest, "mod.c", "line-local\n", "local change")
    _commit_file(origin, "mod.c", "line-remote\n", "remote change")

    resp = client.post(
        "/api/products/pull-code",
        json={
            "git_url": str(origin),
            "git_ref": "main",
            "code_path": str(dest),
            "git_update_mode": "rebase",
        },
    )
    assert resp.status_code == 400
    assert "rebase" in resp.json()["detail"]


# ---------- runner (job 실행) ----------

def test_runner_rebase_product_keeps_cherry_pick(
    db_session: Session, make_virtual_product, fake_genut_repo, tmp_path: Path
) -> None:
    """rebase 프로덕트의 job 실행이 cherry-pick을 유지한 채 원격 최신에서 돈다."""
    vp = make_virtual_product("rebase-vp", mode="cpp", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    repo = Path(vp["repo"])
    code_dir = tmp_path / "code"
    _clone(repo, code_dir)
    _commit_file(code_dir, "src/cherry.cpp", "// cherry\n", "cherry-pick")
    _commit_file(repo, "src/remote.cpp", "// remote\n", "remote change")

    product = Product(
        name=vp["name"],
        product_code=vp["product_code"],
        git_url=vp["git_url"],
        git_ref=vp["git_ref"],
        compile_db_rel=vp["compile_db_rel"],
        out_tests_rel=vp["out_tests_rel"],
        cmake_configure_cmd=vp["cmake_configure_cmd"],
        cmake_build_cmd=vp["cmake_build_cmd"],
        test_run_cmd=vp["test_run_cmd"],
        test_generation_mode=vp["test_generation_mode"],
        code_path=str(code_dir),
        git_update_mode="rebase",
    )
    genut = GenutInstance(
        name="g-rebase",
        repo_url=fake_genut_repo["repo_url"],
        run_command=fake_genut_repo["run_command"],
        ds_assist_credential_key="secret",
        ds_assist_send_system_name="sysX",
    )
    db_session.add_all([product, genut])
    db_session.flush()
    job = Job(product_id=product.id, genut_instance_id=genut.id, file_list=["src/a.cpp"])
    db_session.add(job)
    db_session.commit()

    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path / "ws"))

    assert result.success
    assert (code_dir / "src" / "cherry.cpp").is_file()  # cherry-pick 생존
    assert (code_dir / "src" / "remote.cpp").is_file()  # 원격 최신 반영
