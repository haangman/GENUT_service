"""git clone/checkout/apply 래퍼."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path

from genut_service.runner import subprocess_util


class GitError(Exception):
    """git 명령 실패."""


class PatchError(Exception):
    """patch 적용 실패."""


def _git(
    args: list[str],
    cwd: str | None = None,
    timeout: int = 300,
    on_start: Callable[[object], None] | None = None,
) -> dict:
    """git 명령을 실행하고 {success, returncode, stdout, stderr}를 반환한다.

    on_start가 주어지면 run_streaming으로 실행해 생성된 Popen을 콜백에 노출한다(강제 종료
    등록용 → cancel이 clone/fetch/reset 등 긴 git 작업도 즉시 죽일 수 있게 한다).
    없으면 일반 capture 실행(기존 동작과 동일).
    """
    argv = ["git", *args]
    if on_start is not None:
        return subprocess_util.run_streaming(argv, cwd=cwd, timeout=timeout, on_start=on_start)
    return subprocess_util.run(argv, cwd=cwd, timeout=timeout)


def _run_git(
    args: list[str],
    cwd: str | None = None,
    timeout: int = 300,
    on_start: Callable[[object], None] | None = None,
) -> None:
    res = _git(args, cwd=cwd, timeout=timeout, on_start=on_start)
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")


def clone(
    src: str,
    ref: str,
    dest: Path,
    timeout: int = 300,
    on_start: Callable[[object], None] | None = None,
) -> None:
    """src를 dest로 clone하고 가능하면 ref를 checkout한다(실패 시 기본 브랜치 유지)."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", src, str(dest)], timeout=timeout, on_start=on_start)
    if ref:
        try:
            _run_git(["checkout", ref], cwd=str(dest), timeout=timeout, on_start=on_start)
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
    on_start: Callable[[object], None] | None = None,
    strict: bool = False,
    update_mode: str = "reset",
) -> None:
    """dest에 repo를 제자리 업데이트하거나(없으면) clone한다.

    - `dest/.git`이 있으면 `fetch origin` 후, **HEAD가 이미 원격과 같으면 갱신을
      생략**한다 — reset 전후의 preserve 백업/복원이 트리 전체 복사 2회라, 생성 테스트가
      누적된 out 폴더에서는 이 생략이 실행/사이클당 I/O를 크게 줄인다(이미 적용된 patch
      등 작업 트리 상태도 그대로 유지된다).
    - 변경이 있으면 update_mode에 따라 갱신한다:
      * `reset`(기본): `reset --hard origin/<ref>`로 추적 파일을 최신화한다 — 로컬 전용
        커밋은 삭제된다. `git clean`을 하지 않으므로 **순수 untracked 파일은 보존**되지만,
        `reset --hard`는 **staged(인덱스에 add된) 신규 파일을 삭제**한다. 따라서 생성
        산출물(예: 테스트 출력 폴더)이 GENUT 통합 과정에서 staged 되면 다음 실행의
        reset에서 사라질 수 있다. 이를 막기 위해 `preserve`로 받은 dest 기준 경로들은
        갱신 전에 보관했다가 후에 덮어써(overlay) 복원한다 → staged/untracked 무관 보존.
        fetch/reset 실패는 관용적으로 무시하고 기존 체크아웃을 사용한다 —
        단 `strict=True`면(사용자에게 성공/실패를 정확히 보고해야 하는 다운로드 API 등)
        fetch/rev-parse/reset 실패를 GitError로 올린다.
      * `rebase`: `rebase --autostash origin/<ref>`로 **로컬 전용 커밋(cherry-pick 등)을
        원격 최신 위로 옮겨 유지**한다(로컬 커밋이 없으면 fast-forward = reset과 동일
        결과). 충돌/실패 시 `rebase --abort`로 원상 복구하고 strict 여부와 무관하게
        GitError를 올린다 — 조용히 옛 코드로 실행하면 사용자가 눈치채지 못하기 때문.
    - `.git`이 없으면(있던 비-repo 디렉터리는 정리 후) clone한다(실패 시 GitError).
    """
    dest = Path(dest)
    if (dest / ".git").is_dir():
        fetch = _git(["-C", str(dest), "fetch", "origin"], timeout=timeout, on_start=on_start)
        if fetch["returncode"] == 0:
            target = f"origin/{ref}" if ref else "@{u}"
            local = _git(["-C", str(dest), "rev-parse", "HEAD"], timeout=timeout)
            remote = _git(["-C", str(dest), "rev-parse", target], timeout=timeout)
            if (
                local["success"]
                and remote["success"]
                and local["stdout"].strip() == remote["stdout"].strip()
            ):
                return  # 이미 최신 — 갱신·preserve 백업/복원 생략
            if strict and not remote["success"]:
                detail = (remote.get("stderr") or remote.get("stdout") or "").strip()
                raise GitError(f"git rev-parse {target} failed: {detail}")
            saved = _backup_preserved(dest, preserve)
            if update_mode == "rebase":
                rebase = _git(
                    ["-C", str(dest), "rebase", "--autostash", target],
                    timeout=timeout,
                    on_start=on_start,
                )
                if not rebase["success"]:
                    # 진행 중 rebase를 원상 복구(미시작이면 abort 실패 — 무시)
                    _git(["-C", str(dest), "rebase", "--abort"], timeout=timeout)
                    _restore_preserved(dest, saved)
                    detail = (rebase.get("stderr") or rebase.get("stdout") or "").strip()
                    raise GitError(
                        f"git rebase {target} failed — 로컬 커밋과 원격 변경이 "
                        f"충돌했을 수 있다(수동 해결 필요): {detail}"
                    )
                _restore_preserved(dest, saved)
                return
            reset = _git(
                ["-C", str(dest), "reset", "--hard", target],
                timeout=timeout,
                on_start=on_start,
            )
            _restore_preserved(dest, saved)
            if strict and not reset["success"]:
                detail = (reset.get("stderr") or reset.get("stdout") or "").strip()
                raise GitError(f"git reset --hard {target} failed: {detail}")
        elif strict:
            detail = (fetch.get("stderr") or fetch.get("stdout") or "").strip()
            raise GitError(f"git fetch origin failed: {detail}")
        return
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    clone(url, ref, dest, timeout=timeout, on_start=on_start)


def head_commit(repo_dir: str | Path, timeout: int = 30) -> str:
    """repo의 현재 HEAD 커밋 해시(full)를 반환한다. 실패 시 GitError."""
    res = _git(["-C", str(repo_dir), "rev-parse", "HEAD"], timeout=timeout)
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git rev-parse HEAD failed: {detail}")
    return (res.get("stdout") or "").strip()


def changed_files(
    repo_dir: str | Path, old: str, new: str, timeout: int = 60
) -> list[tuple[str, str]]:
    """두 커밋 사이 변경 파일을 [(status, 상대경로)]로 반환한다. 실패 시 GitError.

    status는 `git diff --name-status`의 상태 토큰(M/A/D/R<유사도>/...) — 리네임은
    `R100`(순수)·`R95`(수정 포함)처럼 유사도가 붙는다. rename/copy는 탭으로 구분된
    마지막(=new-side) 경로를 취한다. 경로는 POSIX 구분자이며, 비ASCII(한글 등)
    파일명이 8진 이스케이프로 인용되지 않도록 core.quotepath를 끈다.
    """
    res = _git(
        [
            "-c", "core.quotepath=false",
            "-C", str(repo_dir),
            "diff", "--name-status", old, new,
        ],
        timeout=timeout,
    )
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git diff --name-status failed: {detail}")
    changes: list[tuple[str, str]] = []
    for line in (res.get("stdout") or "").splitlines():
        parts = line.rstrip().split("\t")
        if len(parts) < 2:
            continue
        changes.append((parts[0], parts[-1]))
    return changes


def diff_new_line_ranges(
    repo_dir: str | Path, old: str, new: str, rel_path: str, timeout: int = 60
) -> list[tuple[int, int]]:
    """한 파일의 두 커밋 간 변경을 new-side 라인 범위(1-based, 양끝 포함)로 반환한다.

    `git diff -U0`의 hunk 헤더 `@@ -a,b +c,d @@`에서 +쪽을 파싱한다. d 생략은 1,
    d==0(순수 삭제)은 삭제 지점 직전 라인 `(max(c,1), max(c,1))`로 귀속시켜
    그 지점을 감싼 함수를 변경으로 판정할 수 있게 한다. 실패 시 GitError.
    """
    res = _git(
        [
            "-c", "core.quotepath=false",
            "-C", str(repo_dir),
            "diff", "-U0", old, new, "--", rel_path,
        ],
        timeout=timeout,
    )
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git diff -U0 failed: {detail}")
    ranges: list[tuple[int, int]] = []
    for line in (res.get("stdout") or "").splitlines():
        match = _HUNK_RE.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = 1 if match.group(2) is None else int(match.group(2))
        if count == 0:
            anchor = max(start, 1)
            ranges.append((anchor, anchor))
        else:
            ranges.append((start, start + count - 1))
    return ranges


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


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


def ls_remote_refs(url: str, pattern: str, timeout: int = 60) -> list[str]:
    """원격에서 pattern에 맞는 ref 이름 목록을 반환한다(실패 시 GitError)."""
    res = _git(["ls-remote", url, pattern], timeout=timeout)
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git ls-remote failed: {detail}")
    refs: list[str] = []
    for line in res["stdout"].splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[1].strip():
            refs.append(parts[1].strip())
    return refs


def fetch_ref(repo_dir: str | Path, url: str, ref: str, timeout: int = 300) -> None:
    """repo_dir로 url의 특정 ref를 fetch한다(이후 FETCH_HEAD로 접근, 실패 시 GitError)."""
    _run_git(["-C", str(repo_dir), "fetch", url, ref], timeout=timeout)


def show_commit(repo_dir: str | Path, rev: str = "FETCH_HEAD", timeout: int = 60) -> str:
    """rev 커밋의 전체 patch 텍스트(git show 출력)를 반환한다(실패 시 GitError)."""
    res = _git(["-C", str(repo_dir), "show", rev], timeout=timeout)
    if not res["success"]:
        detail = (res.get("stderr") or res.get("stdout") or "").strip()
        raise GitError(f"git show {rev} failed: {detail}")
    return res["stdout"]


def commit_subject(repo_dir: str | Path, rev: str = "FETCH_HEAD", timeout: int = 30) -> str:
    """rev 커밋의 제목 한 줄을 반환한다(표시용 — 실패해도 예외 없이 빈 문자열)."""
    res = _git(["-C", str(repo_dir), "show", "-s", "--pretty=%s", rev], timeout=timeout)
    return res["stdout"].strip() if res["success"] else ""


def apply_patch(
    repo_dir: str,
    patch_text: str,
    timeout: int = 120,
    on_start: Callable[[object], None] | None = None,
) -> None:
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
        reverse_check = _git(
            ["apply", "--reverse", "--check", patch_path],
            cwd=repo_dir,
            timeout=timeout,
            on_start=on_start,
        )
        if reverse_check["returncode"] == 0:
            return
        result = _git(["apply", patch_path], cwd=repo_dir, timeout=timeout, on_start=on_start)
        if not result["success"]:
            detail = (result.get("stderr") or result.get("stdout") or "").strip()
            raise PatchError(detail or "patch 적용 실패")
    finally:
        Path(patch_path).unlink(missing_ok=True)
