"""git clone/checkout/apply 래퍼."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class GitError(Exception):
    """git 명령 실패."""


class PatchError(Exception):
    """patch 적용 실패."""


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 300) -> None:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")


def clone(src: str, ref: str, dest: Path, timeout: int = 300) -> None:
    """src를 dest로 clone하고 가능하면 ref를 checkout한다(실패 시 기본 브랜치 유지)."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", src, str(dest)], timeout=timeout)
    if ref:
        try:
            _run_git(["checkout", ref], cwd=str(dest), timeout=timeout)
        except GitError:
            pass


def apply_patch(repo_dir: str, patch_text: str, timeout: int = 120) -> None:
    """unified diff 텍스트를 git apply로 적용한다. 실패 시 PatchError."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".patch", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(patch_text)
        patch_path = handle.name
    try:
        result = subprocess.run(
            ["git", "apply", patch_path],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if result.returncode != 0:
            raise PatchError(result.stderr.strip() or "patch 적용 실패")
    finally:
        Path(patch_path).unlink(missing_ok=True)
