"""잘못된 git ref의 조용한 기본 브랜치 폴백 제거 테스트.

과거: clone의 checkout 실패·ensure_checkout의 origin/<ref> 미해석이 조용히 무시되어
잘못된 ref(오타, 'origin/' 접두 등)가 main 최신으로 대체됐다. 이제 명확한 GitError.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from collections.abc import Iterator

from genut_service.config import get_settings
from genut_service.fs import rmtree_force
from genut_service.runner import git_ops


@pytest.fixture(autouse=True)
def _isolated_workspace(tmp_path: Path) -> Iterator[None]:
    """체크아웃 캐시 경로를 임시 폴더로 격리 — 실제 _workspaces의 개발 잔재와 충돌 방지."""
    settings = get_settings()
    original = settings.workspace_root
    settings.workspace_root = str(tmp_path / "ws")
    yield
    settings.workspace_root = original


def _git(*args: str, cwd: Path) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return r.stdout.strip()


@pytest.fixture()
def origin(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    repo.mkdir()
    _git("-c", "init.defaultBranch=main", "init", cwd=repo)
    _git("config", "user.email", "t@t", cwd=repo)
    _git("config", "user.name", "t", cwd=repo)
    (repo / "marker.txt").write_text("MAIN\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "main", cwd=repo)
    _git("checkout", "-qb", "feature", cwd=repo)
    (repo / "marker.txt").write_text("FEATURE\n", encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "feature", cwd=repo)
    _git("checkout", "-q", "main", cwd=repo)
    return repo


def test_clone_rejects_unknown_ref(origin: Path, tmp_path: Path) -> None:
    with pytest.raises(git_ops.GitError, match="no-such-branch"):
        git_ops.clone(str(origin), "no-such-branch", tmp_path / "dest")


def test_clone_still_checks_out_valid_branch(origin: Path, tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    git_ops.clone(str(origin), "feature", dest)
    assert (dest / "marker.txt").read_text(encoding="utf-8").strip() == "FEATURE"


@pytest.mark.parametrize("bad_ref", ["no-such-branch", "origin/feature"])
def test_ensure_checkout_rejects_unresolvable_ref(
    origin: Path, tmp_path: Path, bad_ref: str
) -> None:
    """fetch 성공 + origin/<ref> 미해석 = 설정 오류 — 비-strict여도 명확히 실패한다.

    'origin/feature'는 사용자가 흔히 넣는 형태(진단 T3) — origin/origin/feature로
    해석돼 과거에는 조용히 main으로 진행됐다.
    """
    dest = tmp_path / "dest"
    git_ops.clone(str(origin), "main", dest)
    head_before = _git("rev-parse", "HEAD", cwd=dest)

    with pytest.raises(git_ops.GitError, match="찾을 수 없다"):
        git_ops.ensure_checkout(str(origin), bad_ref, dest)

    # 체크아웃은 건드리지 않는다(기존 상태 유지)
    assert _git("rev-parse", "HEAD", cwd=dest) == head_before


def test_ensure_checkout_tolerates_fetch_failure(origin: Path, tmp_path: Path) -> None:
    """네트워크성 실패(fetch 실패)는 기존 관용 유지 — 기존 체크아웃으로 진행한다."""
    dest = tmp_path / "dest"
    git_ops.clone(str(origin), "main", dest)
    rmtree_force(origin)  # 원격 소실 → fetch 실패 시나리오 (읽기 전용 git 객체 포함 삭제)

    git_ops.ensure_checkout(str(origin), "main", dest)  # 예외 없이 통과
    assert (dest / "marker.txt").read_text(encoding="utf-8").strip() == "MAIN"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("origin/feature", "feature"),
        ("refs/heads/feature", "feature"),
        ("refs/remotes/origin/feature", "feature"),
        ("  main  ", "main"),
        ("feature", "feature"),
        ("origin/release/1.0", "release/1.0"),  # 접두 1회만 제거 — 슬래시 브랜치명 보존
    ],
)
def test_normalize_git_ref(raw: str, expected: str) -> None:
    from genut_service.schemas.common import normalize_git_ref

    assert normalize_git_ref(raw) == expected


def test_normalize_git_ref_rejects_prefix_only() -> None:
    from genut_service.schemas.common import normalize_git_ref

    with pytest.raises(ValueError):
        normalize_git_ref("origin/")


def test_genut_api_normalizes_repo_ref(client: TestClient) -> None:
    """GENUT 등록/수정 시 `origin/`·`refs/heads/` 접두가 자동 제거되어 저장된다."""
    resp = client.post(
        "/api/genuts",
        json={
            "name": "norm-genut",
            "repo_url": "u",
            "repo_ref": "origin/feature",
            "ds_assist_credential_key": "k",
            "ds_assist_send_system_name": "s",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["repo_ref"] == "feature"

    genut_id = resp.json()["id"]
    upd = client.put(f"/api/genuts/{genut_id}", json={"repo_ref": "refs/heads/dev"})
    assert upd.status_code == 200, upd.text
    assert upd.json()["repo_ref"] == "dev"


def test_product_api_normalizes_git_ref(client: TestClient) -> None:
    resp = client.post(
        "/api/products",
        json={
            "name": "norm-prod",
            "product_code": "NP-1",
            "git_url": "u",
            "git_ref": " origin/main ",
            "compile_db_rel": "build",
            "out_tests_rel": "tests",
            "cmake_configure_cmd": "c",
            "cmake_build_cmd": "b",
            "test_run_cmd": "r",
            "test_generation_mode": "cpp",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["git_ref"] == "main"


def test_tree_api_returns_400_for_bad_ref(
    client: TestClient, db_session: Session, origin: Path
) -> None:
    """요청 페이지 최초 clone에서 잘못된 ref는 500이 아니라 400 + 원인.

    참고: 'origin/feature' 형태는 fresh clone에서는 detached checkout으로 성공하므로
    (내용도 feature와 동일) clone 경로의 오류 대상이 아니다 — 존재하지 않는 ref만 실패.
    """
    from genut_service.db.models import Product

    product = Product(
        name="bad-ref",
        product_code="BR-1",
        git_url=str(origin),
        git_ref="no-such-branch",
        compile_db_rel="build",
        out_tests_rel="tests",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
    )
    db_session.add(product)
    db_session.commit()

    resp = client.get(f"/api/products/{product.id}/tree")
    assert resp.status_code == 400
    assert "no-such-branch" in resp.json()["detail"]
