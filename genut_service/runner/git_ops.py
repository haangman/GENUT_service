"""git clone/checkout/apply 래퍼."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterable
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


def _backup_preserved(dest: Path, preserve: Iterable[str]) -> list[tuple[str, Path, bool]]:
    """preserve 경로들을 임시 위치로 복사해 둔다(reset --hard로부터 보호)."""
    saved: list[tuple[str, Path, bool]] = []
    for rel in preserve:
        if not rel:
            continue
        src = dest / rel
        if not src.exists():
            continue
        holder = Path(tempfile.mkdtemp(prefix="genut_keep_"))
        backup = holder / "data"
        if src.is_dir():
            shutil.copytree(src, backup)
        else:
            shutil.copy2(src, backup)
        saved.append((rel, holder, src.is_dir()))
    return saved


def _restore_preserved(dest: Path, saved: list[tuple[str, Path, bool]]) -> None:
    """보관해 둔 preserve 경로들을 dest에 덮어써(overlay) 복원한다."""
    for rel, holder, is_dir in saved:
        target = dest / rel
        backup = holder / "data"
        try:
            if is_dir:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copytree(backup, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
        finally:
            shutil.rmtree(holder, ignore_errors=True)


def ensure_checkout(
    url: str,
    ref: str,
    dest: Path,
    timeout: int = 300,
    preserve: Iterable[str] = (),
) -> None:
    """dest에 repo를 제자리 업데이트하거나(없으면) clone한다.

    - `dest/.git`이 있으면 `fetch origin` + `reset --hard origin/<ref>`로 추적 파일을 최신화한다.
      `git clean`을 하지 않으므로 **순수 untracked 파일은 보존**되지만, `reset --hard`는
      **staged(인덱스에 add된) 신규 파일을 삭제**한다. 따라서 생성 산출물(예: 테스트 출력
      폴더)이 GENUT 통합 과정에서 staged 되면 다음 실행의 reset에서 사라질 수 있다.
      이를 막기 위해 `preserve`로 받은 dest 기준 경로들은 reset 전에 보관했다가 후에
      덮어써(overlay) 복원한다 → staged/untracked 무관하게 보존된다.
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
            saved = _backup_preserved(dest, preserve)
            subprocess.run(
                ["git", "-C", str(dest), "reset", "--hard", f"origin/{ref}" if ref else "@{u}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
            _restore_preserved(dest, saved)
        return
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    clone(url, ref, dest, timeout=timeout)


def recent_log(repo_dir: str | Path, count: int = 5, timeout: int = 30) -> str:
    """repo의 최근 커밋 로그(oneline)를 반환한다.

    조회에 실패해도 예외를 던지지 않고 안내 문자열을 반환한다(로그 출력용 — job 실행을
    막지 않는다). 형식: `<short-hash> <date> <author> <subject>`.
    """
    try:
        result = subprocess.run(
            [
                "git", "-C", str(repo_dir), "log", "-n", str(count),
                "--pretty=format:%h %ad %an %s", "--date=short",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"(git log 조회 실패: {exc})"
    if result.returncode == 0:
        return result.stdout.strip() or "(커밋 없음)"
    return f"(git log 조회 실패: {(result.stderr or '').strip()[:200]})"


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
