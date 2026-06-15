"""M7: git_ops.apply_patch 동작 테스트."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from genut_service.runner import git_ops


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "main"], path)
    _git(["config", "user.email", "t@example.com"], path)
    _git(["config", "user.name", "tester"], path)
    (path / "a.txt").write_text("one\n", encoding="utf-8")
    _git(["add", "-A"], path)
    _git(["commit", "-m", "init"], path)


def test_apply_patch_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    # 변경 → diff 캡처 → 되돌리기
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    patch = subprocess.run(
        ["git", "diff"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    _git(["checkout", "--", "a.txt"], repo)
    assert (repo / "a.txt").read_text(encoding="utf-8") == "one\n"

    git_ops.apply_patch(str(repo), patch)
    assert (repo / "a.txt").read_text(encoding="utf-8") == "one\ntwo\n"


def test_apply_patch_failure_raises(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    with pytest.raises(git_ops.PatchError):
        git_ops.apply_patch(str(repo), "this is not a valid diff\n")
