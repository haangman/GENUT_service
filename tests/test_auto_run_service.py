"""auto 모드: 누락 테스트 스캔(run_scan_job)·변경 감지(run_diff_job)·job 큐잉 테스트."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.config import get_settings
from genut_service.db.models import Job, Product
from genut_service.enums import JobKind, JobOrigin, JobStatus
from genut_service.services import auto_run_service, function_extractor

AAA_SOURCE = (
    "int bbb(void) { return 1; }\n"
    "int ccc(void) { return 2; }\n"
    "int ddd(void) { return 3; }\n"
)


def _make_root(tmp_path: Path, sources: dict[str, str] | None = None) -> Path:
    """code_path 체크아웃 모사: 소스 + build/compile_commands.json."""
    root = tmp_path / "checkout"
    sources = sources if sources is not None else {"src/aaa.c": AAA_SOURCE}
    for rel, content in sources.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (root / "build").mkdir(parents=True, exist_ok=True)
    compdb = [
        {"directory": str(root / "build"), "command": "cc -c", "file": str((root / rel).resolve())}
        for rel in sources
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    return root


def _make_product(
    session: Session,
    root: Path,
    auto_file_list: list[str] | None = None,
    code_path: str | None = None,
) -> Product:
    product = Product(
        name="auto-demo",
        product_code="auto-demo",
        git_url="https://example.com/repo.git",
        compile_db_rel="build",
        out_tests_rel="unittests",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="c",
        auto_run=True,
        auto_interval_seconds=60,
        auto_file_list=auto_file_list if auto_file_list is not None else ["src/aaa.c"],
        code_path=code_path if code_path is not None else str(root),
    )
    session.add(product)
    session.commit()
    return product


def _prep_job(session: Session, product: Product, kind: JobKind = JobKind.AUTO_SCAN) -> Job:
    job = Job(
        product_id=product.id,
        kind=kind.value,
        origin=JobOrigin.AUTO.value,
        status=JobStatus.RUNNING.value,
    )
    session.add(job)
    session.commit()
    return job


def _genut_jobs(session: Session) -> list[Job]:
    return list(
        session.scalars(
            select(Job).where(Job.kind == JobKind.GENUT.value).order_by(Job.id)
        )
    )


def _write_test_file(root: Path, folder: str, stem: str, filename: str) -> None:
    target = root / folder / stem / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("// generated\n", encoding="utf-8")


class _Emit:
    """emit 콜백 수집기."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []

    def __call__(self, phase: str, level: str, message: str) -> None:
        self.events.append((phase, level, message))

    def messages(self, level: str | None = None) -> list[str]:
        return [m for _, lv, m in self.events if level is None or lv == level]


def test_scan_no_tests_creates_file_level_job(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    product = _make_product(db_session, root)
    scan = _prep_job(db_session, product)
    emit = _Emit()

    summary = auto_run_service.run_scan_job(db_session, scan, product, emit)

    jobs = _genut_jobs(db_session)
    assert len(jobs) == 1
    assert jobs[0].file_list == ["src/aaa.c"]
    assert jobs[0].function_name is None  # 파일 단위 — 함수명 없음
    assert jobs[0].origin == JobOrigin.AUTO.value
    assert jobs[0].status == JobStatus.QUEUED.value
    assert "job 1개 생성" in summary


def test_scan_creates_jobs_only_for_missing_functions(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    # bbb는 성공 폴더(_Test.cpp), ccc는 실패 폴더(_test.cpp) → 누락 함수는 ddd뿐
    _write_test_file(root, "unittests", "aaa", "bbb_Test.cpp")
    _write_test_file(root, "unittests_Fail", "aaa", "ccc_test.cpp")
    product = _make_product(db_session, root)
    scan = _prep_job(db_session, product)
    emit = _Emit()

    auto_run_service.run_scan_job(db_session, scan, product, emit)

    jobs = _genut_jobs(db_session)
    assert [(j.file_list, j.function_name) for j in jobs] == [(["src/aaa.c"], "ddd")]


def test_scan_covers_case_insensitive_test_filenames(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    # 대소문자 변형도 커버로 인정된다
    _write_test_file(root, "unittests", "aaa", "BBB_TEST.cpp")
    _write_test_file(root, "unittests", "aaa", "Ccc_Test.cpp")
    _write_test_file(root, "unittests_Fail", "aaa", "ddd_test.cpp")
    product = _make_product(db_session, root)
    scan = _prep_job(db_session, product)

    auto_run_service.run_scan_job(db_session, scan, product, _Emit())

    assert _genut_jobs(db_session) == []  # 모두 커버 → 생성 없음


def test_scan_skips_functions_with_pending_jobs(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    _write_test_file(root, "unittests", "aaa", "bbb_Test.cpp")  # ccc/ddd 누락
    product = _make_product(db_session, root)
    # ccc는 이미 대기 중 → 스킵, ddd만 새로 큐잉
    pending = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.AUTO.value,
        function_name="ccc",
        file_list=["src/aaa.c"],
        status=JobStatus.QUEUED.value,
    )
    db_session.add(pending)
    db_session.commit()
    scan = _prep_job(db_session, product)
    emit = _Emit()

    summary = auto_run_service.run_scan_job(db_session, scan, product, emit)

    new_jobs = [j for j in _genut_jobs(db_session) if j.id != pending.id]
    assert [(j.function_name) for j in new_jobs] == ["ddd"]
    assert any("스킵(중복)" in m and "ccc" in m for m in emit.messages("info"))
    assert "스킵 1건" in summary


def test_scan_file_level_dedups_against_any_pending_job_of_file(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)  # 테스트 폴더 없음 → 파일 단위 대상
    product = _make_product(db_session, root)
    # 그 파일의 "함수 단위" job이 대기 중이어도 파일 단위 생성은 중복으로 스킵된다
    pending = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.AUTO.value,
        function_name="bbb",
        file_list=["src/aaa.c"],
        status=JobStatus.RUNNING.value,
    )
    db_session.add(pending)
    db_session.commit()
    scan = _prep_job(db_session, product)
    emit = _Emit()

    auto_run_service.run_scan_job(db_session, scan, product, emit)

    assert [j.id for j in _genut_jobs(db_session)] == [pending.id]
    assert any("스킵(중복)" in m for m in emit.messages("info"))


def test_pending_file_level_job_covers_function_requests(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)
    _write_test_file(root, "unittests", "aaa", "bbb_Test.cpp")  # ccc/ddd 누락
    product = _make_product(db_session, root)
    # 파일 단위 job이 대기 중이면 모든 함수 요청이 대체된다
    pending = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.MANUAL.value,
        function_name=None,
        file_list=["src/aaa.c"],
        status=JobStatus.QUEUED.value,
    )
    db_session.add(pending)
    db_session.commit()
    scan = _prep_job(db_session, product)

    summary = auto_run_service.run_scan_job(db_session, scan, product, _Emit())

    assert [j.id for j in _genut_jobs(db_session)] == [pending.id]
    assert "job 0개 생성" in summary


def test_scan_warns_when_source_missing_but_tests_exist(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path, sources={"src/aaa.c": AAA_SOURCE})
    # gone.c는 소스가 없지만 테스트 폴더는 있다 → warn 스킵(파일 단위 아님)
    _write_test_file(root, "unittests", "gone", "old_Test.cpp")
    product = _make_product(db_session, root, auto_file_list=["src/gone.c"])
    scan = _prep_job(db_session, product)
    emit = _Emit()

    summary = auto_run_service.run_scan_job(db_session, scan, product, emit)

    assert _genut_jobs(db_session) == []
    assert any("소스 없음" in m for m in emit.messages("warn"))
    assert "경고 1건" in summary


def test_scan_skips_file_not_in_compile_db(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    (root / "src" / "extra.c").write_text("int eee(void) { return 0; }\n", encoding="utf-8")
    # extra.c는 compile_commands.json에 없다 → 파일 단위 생성 시도 후 warn 스킵
    product = _make_product(db_session, root, auto_file_list=["src/extra.c"])
    scan = _prep_job(db_session, product)
    emit = _Emit()

    auto_run_service.run_scan_job(db_session, scan, product, emit)

    assert _genut_jobs(db_session) == []
    assert any("컴파일DB 미포함" in m for m in emit.messages("warn"))


def test_scan_empty_file_list_is_noop(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    product = _make_product(db_session, root, auto_file_list=[])
    scan = _prep_job(db_session, product)

    summary = auto_run_service.run_scan_job(db_session, scan, product, _Emit())

    assert "대상 0개" in summary
    assert _genut_jobs(db_session) == []


def test_scan_requires_code_path(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    product = _make_product(db_session, root, code_path="")
    product.code_path = None
    db_session.commit()
    scan = _prep_job(db_session, product)

    with pytest.raises(auto_run_service.AutoRunError):
        auto_run_service.run_scan_job(db_session, scan, product, _Emit())


def test_scan_cancellation_raises(db_session: Session, tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    product = _make_product(db_session, root)
    scan = _prep_job(db_session, product)

    with pytest.raises(auto_run_service.AutoRunCanceled):
        auto_run_service.run_scan_job(
            db_session, scan, product, _Emit(), should_cancel=lambda: True
        )


def test_scan_loads_compile_db_once_for_many_enqueues(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    """누락 함수가 K개여도 compile_commands.json은 스캔당 1회만 파싱한다(O(K) 보장)."""
    from genut_service.services import compile_db_service

    root = _make_root(tmp_path)
    _write_test_file(root, "unittests", "aaa", "zzz_Test.cpp")  # 일부 커버 → 함수 단위 경로
    product = _make_product(db_session, root)

    calls: list[int] = []
    original = compile_db_service.load_compile_db

    def counting(*args, **kwargs):  # noqa: ANN001
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        auto_run_service.compile_db_service, "load_compile_db", counting
    )
    scan = _prep_job(db_session, product)

    summary = auto_run_service.run_scan_job(db_session, scan, product, _Emit())

    assert "job 3개 생성" in summary  # bbb/ccc/ddd 모두 누락 → 3건 큐잉
    assert len(calls) == 1  # 큐잉 건수와 무관하게 1회 로드


# ---------------------------------------------------------------------------
# FunctionExtractor(외부 바이너리) 통합
# ---------------------------------------------------------------------------


def _enable_fake_extractor(tmp_path: Path, monkeypatch) -> None:
    """우분투 22.04 + 배치된 바이너리가 있는 환경을 모사한다(실행은 _execute 모킹)."""
    tools = tmp_path / "tools"
    binary = tools / "22_04" / "FunctionExtractor"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"fake-elf")
    monkeypatch.setattr(
        platform,
        "freedesktop_os_release",
        lambda: {"ID": "ubuntu", "VERSION_ID": "22.04"},
        raising=False,
    )
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tools))
    function_extractor.find_extractor.cache_clear()


def test_scan_uses_function_extractor_binary(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    """바이너리가 있으면 내장 파서 대신 바이너리 출력으로 누락 함수를 판정한다."""
    root = _make_root(tmp_path)
    _write_test_file(root, "unittests", "aaa", "bbb_Test.cpp")  # bbb만 커버
    product = _make_product(db_session, root)
    _enable_fake_extractor(tmp_path, monkeypatch)
    output = json.dumps(
        [
            {"name": "bbb", "code": "int bbb(void){\n}", "line": 1},
            {"name": "ccc", "code": "int ccc(void){\n}", "line": 2},
            {"name": "ddd", "code": "int ddd(void){\n}", "line": 3},
        ]
    )
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {"success": True, "returncode": 0, "stdout": output, "stderr": ""},
    )
    scan = _prep_job(db_session, product)
    emit = _Emit()

    auto_run_service.run_scan_job(db_session, scan, product, emit)

    jobs = _genut_jobs(db_session)
    assert [j.function_name for j in jobs] == ["ccc", "ddd"]
    # job 로그에 어떤 추출기를 썼는지 남는다
    assert any("FunctionExtractor(22_04)" in m for m in emit.messages("info"))


def test_scan_extractor_failure_propagates(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    """바이너리가 있는 환경에서 실행 실패는 폴백 없이 전파 → 준비 job FAILED."""
    root = _make_root(tmp_path)
    _write_test_file(root, "unittests", "aaa", "bbb_Test.cpp")  # 함수 추출 경로 진입
    product = _make_product(db_session, root)
    _enable_fake_extractor(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {"success": False, "returncode": 1, "stdout": "", "stderr": "boom"},
    )
    scan = _prep_job(db_session, product)

    with pytest.raises(function_extractor.ExtractorError):
        auto_run_service.run_scan_job(db_session, scan, product, _Emit())


def test_diff_extractor_failure_keeps_baseline(
    db_session: Session, tmp_path: Path, monkeypatch
) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    baseline = _head(root)
    product.last_scanned_commit = baseline
    db_session.commit()
    (root / "src" / "aaa.c").write_text(
        AAA_SOURCE.replace("return 2;", "return 22;"), encoding="utf-8"
    )
    _git_commit_all(root, "change ccc")

    _enable_fake_extractor(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {"success": False, "returncode": 2, "stdout": "", "stderr": "boom"},
    )
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    with pytest.raises(function_extractor.ExtractorError):
        auto_run_service.run_diff_job(db_session, diff, product, _Emit())
    assert product.last_scanned_commit == baseline  # 실패 시 기준 미전진 → 다음 주기 재시도


# ---------------------------------------------------------------------------
# 변경 함수 감지 (run_diff_job)
# ---------------------------------------------------------------------------


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _git_init(root: Path) -> None:
    _git(["init", "-b", "main"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "tester"], root)
    _git(["add", "-A"], root)
    _git(["commit", "-m", "init"], root)


def _git_commit_all(root: Path, message: str) -> None:
    _git(["add", "-A"], root)
    _git(["commit", "-m", message], root)


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _make_git_root(tmp_path: Path, sources: dict[str, str] | None = None) -> Path:
    """git repo인 code_path 체크아웃 모사(원격 없음 → fetch는 관용 무시됨)."""
    root = _make_root(tmp_path, sources)
    _git_init(root)
    return root


def test_diff_first_run_records_baseline(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    summary = auto_run_service.run_diff_job(db_session, diff, product, _Emit())

    assert "최초 실행" in summary
    assert product.last_scanned_commit == _head(root)
    assert _genut_jobs(db_session) == []  # diff job은 만들지 않는다


def test_diff_no_change_keeps_baseline(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    baseline = _head(root)
    product.last_scanned_commit = baseline
    db_session.commit()
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    summary = auto_run_service.run_diff_job(db_session, diff, product, _Emit())

    assert "변경 없음" in summary
    assert product.last_scanned_commit == baseline
    assert _genut_jobs(db_session) == []


def test_diff_detects_changed_function_only(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    product.last_scanned_commit = _head(root)
    db_session.commit()

    # ccc의 본문만 수정(2번째 줄) — bbb/ddd는 그대로
    (root / "src" / "aaa.c").write_text(
        "int bbb(void) { return 1; }\n"
        "int ccc(void) { return 22; }\n"
        "int ddd(void) { return 3; }\n",
        encoding="utf-8",
    )
    _git_commit_all(root, "change ccc")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    summary = auto_run_service.run_diff_job(db_session, diff, product, emit)

    jobs = _genut_jobs(db_session)
    assert [(j.file_list, j.function_name) for j in jobs] == [(["src/aaa.c"], "ccc")]
    assert product.last_scanned_commit == _head(root)  # 성공 → 기준 전진
    assert "job 1개 생성" in summary


def test_diff_ignores_files_outside_auto_list(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(
        tmp_path, sources={"src/aaa.c": AAA_SOURCE, "src/other.c": "int zzz(void) { return 0; }\n"}
    )
    product = _make_product(db_session, root)  # auto_file_list = ["src/aaa.c"]
    product.last_scanned_commit = _head(root)
    db_session.commit()

    (root / "src" / "other.c").write_text("int zzz(void) { return 9; }\n", encoding="utf-8")
    _git_commit_all(root, "change other")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    summary = auto_run_service.run_diff_job(db_session, diff, product, _Emit())

    assert _genut_jobs(db_session) == []
    assert "대상 파일 변경 0건" in summary
    assert product.last_scanned_commit == _head(root)  # 기준은 전진


def test_diff_change_outside_functions_creates_no_job(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    product.last_scanned_commit = _head(root)
    db_session.commit()

    # 함수 밖(파일 맨 위)에 주석 한 줄 추가
    original = (root / "src" / "aaa.c").read_text(encoding="utf-8")
    (root / "src" / "aaa.c").write_text("// header comment\n" + original, encoding="utf-8")
    _git_commit_all(root, "add comment")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    auto_run_service.run_diff_job(db_session, diff, product, emit)

    assert _genut_jobs(db_session) == []
    assert any("함수 영역 밖 변경" in m for m in emit.messages("info"))


def test_diff_added_file_is_delegated_to_scan(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(
        db_session, root, auto_file_list=["src/aaa.c", "src/newer.c"]
    )
    product.last_scanned_commit = _head(root)
    db_session.commit()

    (root / "src" / "newer.c").write_text("int nnn(void) { return 0; }\n", encoding="utf-8")
    _git_commit_all(root, "add newer.c")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    auto_run_service.run_diff_job(db_session, diff, product, emit)

    assert _genut_jobs(db_session) == []  # 신규(A)는 누락 스캔에 위임
    assert any("누락 스캔에 위임" in m for m in emit.messages("info"))
    assert product.last_scanned_commit == _head(root)


def test_diff_lost_baseline_rebases_to_head(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    product.last_scanned_commit = "0" * 40  # 존재하지 않는 커밋(소실 모사)
    db_session.commit()
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    summary = auto_run_service.run_diff_job(db_session, diff, product, emit)

    assert "기준 커밋 재설정" in summary
    assert product.last_scanned_commit == _head(root)
    assert any("재기준" in m for m in emit.messages("warn"))


def test_diff_changed_function_dedups_pending_job(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    product.last_scanned_commit = _head(root)
    db_session.commit()
    pending = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.AUTO.value,
        function_name="ccc",
        file_list=["src/aaa.c"],
        status=JobStatus.QUEUED.value,
    )
    db_session.add(pending)
    db_session.commit()

    (root / "src" / "aaa.c").write_text(
        AAA_SOURCE.replace("return 2;", "return 22;"), encoding="utf-8"
    )
    _git_commit_all(root, "change ccc")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    summary = auto_run_service.run_diff_job(db_session, diff, product, _Emit())

    assert [j.id for j in _genut_jobs(db_session)] == [pending.id]
    assert "스킵 1건" in summary


def test_diff_registers_git_processes_for_cancellation(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root)
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    procs: list[object] = []

    auto_run_service.run_diff_job(
        db_session, diff, product, _Emit(), on_process=procs.append
    )

    assert procs  # fetch 등 git 서브프로세스가 등록 콜백에 노출 → 취소 시 즉시 kill 가능


def test_diff_pure_rename_creates_no_jobs(db_session: Session, tmp_path: Path) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root, auto_file_list=["src/bbb.c"])
    product.last_scanned_commit = _head(root)
    db_session.commit()

    _git(["mv", "src/aaa.c", "src/bbb.c"], root)
    _git_commit_all(root, "pure rename")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    auto_run_service.run_diff_job(db_session, diff, product, emit)

    assert _genut_jobs(db_session) == []  # 내용 동일 + stem 기준 테스트 매칭 유지 → 재생성 불필요
    assert any("순수 리네임" in m for m in emit.messages("info"))


def test_diff_rename_with_modification_regenerates_all_functions(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_git_root(tmp_path)
    product = _make_product(db_session, root, auto_file_list=["src/bbb.c"])
    product.last_scanned_commit = _head(root)
    db_session.commit()

    _git(["mv", "src/aaa.c", "src/bbb.c"], root)
    (root / "src" / "bbb.c").write_text(
        AAA_SOURCE.replace("return 2;", "return 22;"), encoding="utf-8"
    )
    # 새 경로가 compile db에 잡히도록 갱신(basename 매칭)
    (root / "build" / "compile_commands.json").write_text(
        json.dumps(
            [{"directory": str(root / "build"), "command": "cc -c", "file": str(root / "src" / "bbb.c")}]
        ),
        encoding="utf-8",
    )
    _git_commit_all(root, "rename with edit")
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)
    emit = _Emit()

    auto_run_service.run_diff_job(db_session, diff, product, emit)

    # 리네임+수정은 라인 대응이 어려워 파일의 전 함수를 재생성한다
    jobs = _genut_jobs(db_session)
    assert [(j.file_list, j.function_name) for j in jobs] == [
        (["src/bbb.c"], "bbb"),
        (["src/bbb.c"], "ccc"),
        (["src/bbb.c"], "ddd"),
    ]
    assert any("리네임+수정" in m for m in emit.messages("info"))


def test_diff_non_git_code_path_raises_and_keeps_baseline(
    db_session: Session, tmp_path: Path
) -> None:
    root = _make_root(tmp_path)  # git repo 아님 → ensure_checkout이 재clone 시도
    product = _make_product(db_session, root)
    # clone도 실패하도록 존재하지 않는 로컬 경로를 git_url로 둔다(네트워크 접근 없음)
    product.git_url = str(tmp_path / "no-such-repo")
    db_session.commit()
    diff = _prep_job(db_session, product, kind=JobKind.AUTO_DIFF)

    from genut_service.runner.git_ops import GitError

    with pytest.raises(GitError):
        auto_run_service.run_diff_job(db_session, diff, product, _Emit())
    assert product.last_scanned_commit is None  # 실패 시 기준 미전진
