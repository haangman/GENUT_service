"""git clone/checkout/apply 래퍼."""

from __future__ import annotations

import shutil
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


def ensure_checkout(url: str, ref: str, dest: Path, timeout: int = 300) -> None:
    """dest에 repo를 제자리 업데이트하거나(없으면) clone한다.

    - `dest/.git`이 있으면 `fetch origin` + `reset --hard origin/<ref>`로 추적 파일만 최신화한다.
      **git clean을 하지 않으므로 untracked 파일(생성된 테스트 등)은 보존**된다.
      fetch/reset 실패는 관용적으로 무시하고 기존 체크아웃을 사용한다.
    - `.git`이 없으면(있던 비-repo 디렉터리는 정리 후) clone한다(실패 시 GitError).
    """
    dest = Path(dest)
    if (dest / ".git").is_dir():
        fetch = subprocess.run(
            ["git", "-C", str(dest), "fetch", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        if fetch.returncode == 0:
            subprocess.run(
                ["git", "-C", str(dest), "reset", "--hard", f"origin/{ref}" if ref else "@{u}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        return
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    clone(url, ref, dest, timeout=timeout)


def apply_patch(repo_dir: str, patch_text: str, timeout: int = 120) -> None:
    """unified diff 텍스트를 git apply로 적용한다(멱등). 실패 시 PatchError.

    이미 적용된 패치(`git apply --reverse --check` 성공)는 건너뛴다 →
    영속 경로에서 reset 후 재적용 시 "이미 적용/이미 존재" 충돌을 방지한다.
    """
    with tempfile.NamedTemporaryFile(
        "w", suffix=".patch", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(patch_text)
        patch_path = handle.name
    try:
        # 이미 적용되어 있으면(역적용이 가능하면) 건너뛴다
        reverse_check = subprocess.run(
            ["git", "apply", "--reverse", "--check", patch_path],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if reverse_check.returncode == 0:
            return
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
