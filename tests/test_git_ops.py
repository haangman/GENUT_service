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


def test_recent_log_returns_commit_subjects(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(["commit", "-am", "second commit"], repo)
    out = git_ops.recent_log(repo)
    assert "init" in out
    assert "second commit" in out


def test_recent_log_tolerates_non_repo(tmp_path: Path) -> None:
    # git repo가 아니어도 예외 없이 안내 문자열을 반환한다
    out = git_ops.recent_log(tmp_path)
    assert "git log 조회 실패" in out


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_head_commit_returns_full_hash(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    first = git_ops.head_commit(repo)
    assert first == _head(repo)
    assert len(first) == 40

    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(["commit", "-am", "second"], repo)
    second = git_ops.head_commit(repo)
    assert second == _head(repo)
    assert second != first


def test_head_commit_non_repo_raises(tmp_path: Path) -> None:
    with pytest.raises(git_ops.GitError):
        git_ops.head_commit(tmp_path)


def test_changed_files_reports_statuses(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "del.txt").write_text("bye\n", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "keep.c").write_text("int x;\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "baseline"], repo)
    old = _head(repo)

    (repo / "a.txt").write_text("one\ntwo\n", encoding="utf-8")  # M
    (repo / "del.txt").unlink()  # D
    (repo / "src" / "new.c").write_text("int y;\n", encoding="utf-8")  # A
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "changes"], repo)
    new = _head(repo)

    changes = git_ops.changed_files(repo, old, new)
    assert ("M", "a.txt") in changes
    assert ("D", "del.txt") in changes
    assert ("A", "src/new.c") in changes  # 경로는 POSIX 구분자


def test_changed_files_unknown_commit_raises(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    with pytest.raises(git_ops.GitError):
        git_ops.changed_files(repo, "0" * 40, "HEAD")


def test_changed_files_handles_non_ascii_names(tmp_path: Path) -> None:
    # core.quotepath 기본값(true)이면 한글 파일명이 8진 이스케이프로 인용되어
    # 경로 매칭이 깨진다 — quotepath를 끄고 원문 경로를 받는지 확인한다.
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "모듈.c").write_text("int one(void) { return 1; }\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "korean file"], repo)
    old = _head(repo)

    (repo / "모듈.c").write_text("int one(void) { return 11; }\n", encoding="utf-8")
    _git(["commit", "-am", "edit korean file"], repo)

    changes = git_ops.changed_files(repo, old, _head(repo))
    assert ("M", "모듈.c") in changes


def test_changed_files_reports_rename_with_similarity(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "old_name.c").write_text(
        "int bbb(void) { return 1; }\nint ccc(void) { return 2; }\n", encoding="utf-8"
    )
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "baseline"], repo)
    old = _head(repo)

    _git(["mv", "old_name.c", "new_name.c"], repo)
    _git(["commit", "-m", "rename"], repo)

    changes = git_ops.changed_files(repo, old, _head(repo))
    assert len(changes) == 1
    status, path = changes[0]
    assert status == "R100"  # 순수 리네임은 유사도 100
    assert path == "new_name.c"  # new-side 경로


def test_diff_new_line_ranges_modified_deleted_added(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / "f.c"
    target.write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "baseline"], repo)
    old = _head(repo)

    # l2 수정, l4 삭제(순수 삭제), 끝에 extra 추가
    target.write_text("l1\nL2\nl3\nl5\nextra\n", encoding="utf-8")
    _git(["commit", "-am", "edit"], repo)
    new = _head(repo)

    ranges = git_ops.diff_new_line_ranges(repo, old, new, "f.c")
    # 수정=(2,2), 순수 삭제는 new-side 직전 라인으로 귀속=(3,3), 추가=(5,5)
    assert ranges == [(2, 2), (3, 3), (5, 5)]


def test_diff_new_line_ranges_multiline_hunk(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    target = repo / "f.c"
    target.write_text("l1\nl2\nl3\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "baseline"], repo)
    old = _head(repo)

    # l2를 3줄로 교체 → 한 hunk의 new-side가 (2,4)
    target.write_text("l1\na\nb\nc\nl3\n", encoding="utf-8")
    _git(["commit", "-am", "expand"], repo)
    new = _head(repo)

    assert git_ops.diff_new_line_ranges(repo, old, new, "f.c") == [(2, 4)]


def test_git_ops_clone_invokes_on_start_for_cancellation(tmp_path: Path) -> None:
    """on_start가 주어지면 git이 등록 가능한 Popen으로 실행된다(취소 시 kill 대상)."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    procs: list[object] = []
    git_ops.clone(str(origin), "main", tmp_path / "work", on_start=lambda p: procs.append(p))
    assert procs  # clone이 Popen을 콜백에 노출 → process_registry 등록이 가능
    assert (tmp_path / "work" / ".git").is_dir()


def test_ensure_checkout_preserve_keeps_staged_output(tmp_path: Path) -> None:
    """reset --hard는 staged 신규 파일을 지우지만 preserve로 지정한 폴더는 보존된다."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    (origin / "out").mkdir()
    (origin / "out" / ".gitkeep").write_text("", encoding="utf-8")
    _git(["add", "-A"], origin)
    _git(["commit", "-m", "add out"], origin)

    work = tmp_path / "work"
    git_ops.ensure_checkout(str(origin), "main", work)  # 최초 clone
    out = work / "out"

    # 직전 실행이 생성하고 staging까지 한 산출물 모사
    (out / "gen_Test.cpp").write_text("generated\n", encoding="utf-8")
    _git(["add", str(out / "gen_Test.cpp")], work)

    # preserve 없이 재체크아웃하면 staged 신규 파일은 사라진다(회귀의 근본 원인 입증)
    git_ops.ensure_checkout(str(origin), "main", work)
    assert not (out / "gen_Test.cpp").exists()

    # 다시 생성·staging 후 preserve=["out"]로 재체크아웃하면 보존된다
    (out / "gen_Test.cpp").write_text("generated\n", encoding="utf-8")
    _git(["add", str(out / "gen_Test.cpp")], work)
    git_ops.ensure_checkout(str(origin), "main", work, preserve=["out"])
    assert (out / "gen_Test.cpp").is_file()  # 생성물 보존
    assert (out / ".gitkeep").is_file()  # 커밋 baseline 도 유지
