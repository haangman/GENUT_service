"""M7: GENUT runner (subprocess, fake GENUT + 가상 프로덕트) 테스트."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Patch, Product
from genut_service.runner import genut_runner

_PRODUCT_FIELDS = (
    "name",
    "product_code",
    "git_url",
    "git_ref",
    "compile_db_rel",
    "out_tests_rel",
    "cmake_configure_cmd",
    "cmake_build_cmd",
    "test_run_cmd",
    "test_generation_mode",
)


def _setup(db_session: Session, vp: dict, genut_repo: dict, file_list, function_name=None):
    product = Product(**{key: vp[key] for key in _PRODUCT_FIELDS})
    for index, patch in enumerate(vp["patches"]):
        product.patches.append(
            Patch(order_index=patch.get("order_index", index), name=patch["name"], content=patch["content"])
        )
    genut = GenutInstance(
        name=f"g-{vp['name']}",
        repo_url=genut_repo["repo_url"],
        run_command=genut_repo["run_command"],
        ds_assist_credential_key="secret",
        ds_assist_send_system_name="sysX",
        ds_assist_user_id="userX",
        max_attempts=5,
    )
    db_session.add_all([product, genut])
    db_session.flush()
    job = Job(
        product_id=product.id,
        genut_instance_id=genut.id,
        file_list=file_list,
        function_name=function_name,
    )
    db_session.add(job)
    db_session.commit()
    return product, genut, job


def _read_result(run_result) -> dict:
    return json.loads((Path(run_result.out_dir) / "result.json").read_text(encoding="utf-8"))


def test_runner_success_generates_50_50(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product("ok", mode="cpp", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert result.success
    assert result.generated_files
    data = _read_result(result)
    assert data["counts"]["positive"] == data["counts"]["negative"]
    assert data["counts"]["total"] > 0


def test_runner_filelist_contains_only_included_absolute(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    vp = make_virtual_product("flist", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    lines = (tmp_path / f"job_{job.id}" / "filelist.txt").read_text(encoding="utf-8").split()
    assert len(lines) == 1
    assert os.path.isabs(lines[0])
    assert lines[0].endswith("a.cpp")


def test_runner_env_provenance(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product("prov", mode="cpp", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    env_seen = _read_result(result)["env_seen"]
    assert env_seen["TEST_GENERATION_MODE"] == "cpp"
    assert env_seen["DS_ASSIST_SEND_SYSTEM_NAME"] == "sysX"
    assert env_seen["DS_ASSIST_USER_ID"] == "userX"
    assert env_seen["TEST_RUN_CMD"] == "echo test"


def test_runner_function_name_restricts(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product(
        "fn", sources={"src/a.cpp": "// @genut-fn: foo\n// @genut-fn: bar\n"}
    )
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"], function_name="foo")
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert _read_result(result)["functions"] == ["foo"]
    assert all("foo" in name for name in result.generated_files)


def test_runner_debug_and_assure_artifacts(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    vp = make_virtual_product("dbg", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(
        job, product, genut, workspace_root=str(tmp_path), debug=True, enable_assure=True
    )
    out = Path(result.out_dir)
    assert (out / "genut_debug.log").is_file()
    assert (out / "assure" / "assure_summary.json").is_file()


def test_runner_hard_fail(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product(
        "bad", sources={"src/a.cpp": "// @genut-fn: foo\n"}, scenario={"outcome": "hard_fail"}
    )
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert result.success is False
    assert result.result_summary is not None
    assert "failed" in result.result_summary


def test_masked_env_text_masks_secret() -> None:
    from genut_service.runner.genut_runner import _masked_env_text

    text = _masked_env_text(
        {"TEST_GENERATION_MODE": "cpp", "DS_ASSIST_CREDENTIAL_KEY": "super-secret"}
    )
    assert "TEST_GENERATION_MODE=cpp" in text
    assert "DS_ASSIST_CREDENTIAL_KEY=********" in text
    assert "super-secret" not in text


def test_runner_persistent_code_path_preserves_generated(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    vp = make_virtual_product("persist", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    code_dir = tmp_path / "persist_checkout"
    product.code_path = str(code_dir)
    db_session.commit()

    # 1차 실행: 영속 경로에 clone + 테스트 생성
    r1 = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert r1.success
    out = Path(r1.out_dir)
    assert out == (code_dir / "tests" / "generated").resolve()  # 영속 경로 안
    assert list(out.glob("test_*"))

    # 이전 생성물 모사: untracked 더미 + staged(git add) 더미 둘 다 추가.
    # 실 GENUT가 생성 테스트를 프로젝트에 통합하며 staging 하는 경우를 모사한다.
    keep = out / "keepme_Test.cpp"
    keep.write_text("// previously generated\n", encoding="utf-8")
    staged = out / "staged_Test.cpp"
    staged.write_text("// staged by integration\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(code_dir), "add", str(staged)],
        capture_output=True, text=True, check=True,
    )

    # 2차 실행(같은 code_path) → 제자리 업데이트(fetch+reset). out 폴더는 보존되어야 한다.
    job2 = Job(product_id=product.id, genut_instance_id=genut.id, file_list=["src/a.cpp"])
    db_session.add(job2)
    db_session.commit()
    r2 = genut_runner.run(job2, product, genut, workspace_root=str(tmp_path))
    assert r2.success
    assert keep.is_file()  # untracked 생성물 보존
    assert staged.is_file()  # staged 생성물도 보존(reset --hard로부터 보호 — 회귀 방지)


class _RecordingExecutor:
    """venv 준비 로직 단위 테스트용 가짜 executor (실제 venv 생성 안 함)."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def to_exec_path(self, path) -> str:  # noqa: ANN001
        return str(path)

    def base_python(self) -> str:
        return "BASEPY"

    def venv_python(self, venv_dir) -> str:  # noqa: ANN001
        return str(Path(venv_dir) / "bin" / "python")

    def run(self, argv, cwd, timeout, on_line=None, on_start=None):  # noqa: ANN001, ARG002
        self.calls.append(list(argv))
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}


def test_with_venv_python_substitutes_leading_interpreter() -> None:
    assert genut_runner._with_venv_python(["python", "-m", "genut"], "/v/py") == [
        "/v/py", "-m", "genut",
    ]
    assert genut_runner._with_venv_python(["/usr/bin/python3", "x.py"], "/v/py") == ["/v/py", "x.py"]
    # python이 아닌 선행 토큰(콘솔 스크립트 등)은 그대로 둔다
    assert genut_runner._with_venv_python(["genut", "run"], "/v/py") == ["genut", "run"]


def test_prepare_venv_creates_and_installs_requirements(tmp_path) -> None:
    genut_dir = tmp_path / "genut"
    genut_dir.mkdir()
    (genut_dir / "requirements.txt").write_text("# none\n", encoding="utf-8")
    ex = _RecordingExecutor()
    venv_py = genut_runner._prepare_venv(ex, genut_dir, timeout=60, ev=lambda *a: None, stream=False)
    # 1) venv 생성, 2) requirements 설치(venv python으로)
    assert ex.calls[0][:3] == ["BASEPY", "-m", "venv"]
    assert ex.calls[1][:4] == [venv_py, "-m", "pip", "install"]
    assert venv_py.endswith("python")


def test_prepare_venv_skips_install_without_requirements(tmp_path) -> None:
    genut_dir = tmp_path / "genut"
    genut_dir.mkdir()
    ex = _RecordingExecutor()
    genut_runner._prepare_venv(ex, genut_dir, timeout=60, ev=lambda *a: None, stream=False)
    assert len(ex.calls) == 1  # venv 생성만, pip install 없음


def test_host_venv_python_stays_inside_venv(tmp_path) -> None:
    """venv python 경로는 venv 디렉터리 안을 가리켜야 한다(symlink resolve 금지).

    리눅스에서 .resolve()로 bin/python symlink를 따라가면 베이스 python(외부 관리)이 되어
    pip가 externally-managed 오류를 낸다. 이 회귀를 방지한다.
    """
    import subprocess
    import sys

    from genut_service.runner.executors import HostExecutor

    venv_dir = tmp_path / ".venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True, capture_output=True)

    vpy = HostExecutor().venv_python(venv_dir)
    assert os.path.exists(vpy)
    venv_abs = os.path.abspath(venv_dir)
    # venv python은 venv 디렉터리 하위여야 한다(베이스로 빠지면 commonpath가 달라짐)
    assert os.path.commonpath([os.path.abspath(vpy), venv_abs]) == venv_abs


def test_prepare_venv_reuses_existing(tmp_path) -> None:
    genut_dir = tmp_path / "genut"
    genut_dir.mkdir()
    # 이미 만들어진 venv 표식(pyvenv.cfg)
    (genut_dir / ".venv").mkdir()
    (genut_dir / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (genut_dir / "requirements.txt").write_text("# none\n", encoding="utf-8")
    ex = _RecordingExecutor()
    genut_runner._prepare_venv(ex, genut_dir, timeout=60, ev=lambda *a: None, stream=False)
    # venv 생성 호출이 없어야 한다(재사용)
    assert all(not (len(c) >= 3 and c[1] == "-m" and c[2] == "venv") for c in ex.calls)
    # requirements 설치는 여전히 수행
    assert any(c[1:4] == ["-m", "pip", "install"] for c in ex.calls)


def test_prepare_venv_raises_on_failure(tmp_path) -> None:
    genut_dir = tmp_path / "genut"
    genut_dir.mkdir()

    class _FailExecutor(_RecordingExecutor):
        def run(self, argv, cwd, timeout, on_line=None, on_start=None):  # noqa: ANN001, ARG002
            return {"success": False, "returncode": 1, "stdout": "", "stderr": "boom"}

    import pytest

    with pytest.raises(genut_runner.VenvError):
        genut_runner._prepare_venv(_FailExecutor(), genut_dir, timeout=60, ev=lambda *a: None, stream=False)


def test_runner_venv_setup_creates_venv_and_runs(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """use_venv=True면 실제 .venv를 만들고 그 python으로 GENUT를 실행한다."""
    vp = make_virtual_product("venv", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path), use_venv=True)
    assert result.success
    venv_dir = tmp_path / f"job_{job.id}" / "genut" / ".venv"
    assert venv_dir.is_dir()  # 가상환경이 생성됨


def test_runner_venv_reused_on_second_run(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """영속 경로의 .venv는 1차에 생성되고, 2차에는 재사용된다(재생성 안 함)."""
    vp = make_virtual_product("venvreuse", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    genut.code_path = str(tmp_path / "genut_persist")  # 영속 → 같은 genut_dir 재사용
    db_session.commit()

    ev1: list[str] = []
    r1 = genut_runner.run(
        job, product, genut, workspace_root=str(tmp_path), use_venv=True,
        on_event=lambda p, l, m: ev1.append(m),
    )
    assert r1.success
    assert any("생성" in m and ".venv" in m for m in ev1)
    # ensure_checkout(영속 code_path) 경로에서도 git log가 emit된다
    assert any("GENUT git log" in m for m in ev1)
    # 디스크에 venv 표식이 실제로 생성됨 (GENUT는 저장경로/GENUT 하위)
    persist_venv = tmp_path / "genut_persist" / "GENUT" / ".venv" / "pyvenv.cfg"
    assert persist_venv.is_file()

    job2 = Job(product_id=product.id, genut_instance_id=genut.id, file_list=["src/a.cpp"])
    db_session.add(job2)
    db_session.commit()
    ev2: list[str] = []
    r2 = genut_runner.run(
        job2, product, genut, workspace_root=str(tmp_path), use_venv=True,
        on_event=lambda p, l, m: ev2.append(m),
    )
    assert r2.success
    assert any("기존 .venv 재사용" in m for m in ev2)
    assert not any("재사용" not in m and "생성" in m and ".venv" in m for m in ev2)


def test_runner_clones_assure_at_same_depth(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """assure_repo_url가 있으면 ASSURE를 GENUT 코드와 같은 depth(형제)로 받고 git log를 남긴다."""
    vp = make_virtual_product("assure", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    genut.assure_repo_url = fake_genut_repo["repo_url"]  # 아무 git repo면 충분
    db_session.commit()

    events: list[tuple[str, str]] = []
    result = genut_runner.run(
        job, product, genut, workspace_root=str(tmp_path),
        on_event=lambda phase, level, msg: events.append((phase, msg)),
    )
    assert result.success
    genut_dir = tmp_path / f"job_{job.id}" / "genut"
    assure_dir = tmp_path / f"job_{job.id}" / "genut_assure"
    assert (genut_dir / ".git").is_dir()
    assert (assure_dir / ".git").is_dir()  # ASSURE가 받아짐
    assert assure_dir.parent == genut_dir.parent  # GENUT와 같은 depth(형제)
    assert any("ASSURE git log" in m for _, m in events)


def test_runner_persistent_code_path_puts_genut_and_assure_in_subdirs(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """genut.code_path가 있으면 GENUT는 저장경로/GENUT, ASSURE는 저장경로/ASSURE에 받는다."""
    vp = make_virtual_product("subdirs", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    code_root = tmp_path / "genut_store"
    genut.code_path = str(code_root)
    genut.assure_repo_url = fake_genut_repo["repo_url"]  # 아무 git repo면 충분
    db_session.commit()

    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert result.success
    assert (code_root / "GENUT" / ".git").is_dir()   # GENUT → 저장경로/GENUT
    assert (code_root / "ASSURE" / ".git").is_dir()  # ASSURE → 저장경로/ASSURE
    # 저장경로 루트에 직접 받지 않고, _assure 형제 디렉터리도 만들지 않는다
    assert not (code_root / ".git").is_dir()
    assert not (tmp_path / "genut_store_assure").exists()


def test_runner_should_cancel_aborts_early(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """should_cancel이 True면 무거운 단계(clone 등) 전에 Canceled로 중단한다(협조적 취소)."""
    vp = make_virtual_product("coopcxl", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    with pytest.raises(genut_runner.Canceled):
        genut_runner.run(
            job, product, genut, workspace_root=str(tmp_path), should_cancel=lambda: True
        )


def test_runner_skips_assure_when_url_absent(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    vp = make_virtual_product("noassure", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])  # assure_repo_url 없음
    events: list[tuple[str, str]] = []
    genut_runner.run(
        job, product, genut, workspace_root=str(tmp_path),
        on_event=lambda phase, level, msg: events.append((phase, msg)),
    )
    assert not (tmp_path / f"job_{job.id}" / "genut_assure").exists()
    assert not any("ASSURE" in m for _, m in events)


def test_runner_on_process_can_kill(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    """on_process로 받은 GENUT 서브프로세스를 죽이면 실행이 실패로 끝난다(강제 종료 기반)."""
    vp = make_virtual_product(
        "kill",
        sources={"src/a.cpp": "// @genut-fn: foo\n"},
        scenario={"outcome": "success", "sleep_seconds": 30},
    )
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])

    def on_process(proc):
        proc.kill()  # 시작하자마자 강제 종료

    result = genut_runner.run(
        job,
        product,
        genut,
        workspace_root=str(tmp_path),
        on_event=lambda *a: None,  # 스트리밍 경로 활성화 → on_start(on_process) 호출됨
        on_process=on_process,
    )
    assert result.success is False  # sleep 30이지만 즉시 종료되어 실패


def test_runner_uses_compile_dp_path_flag(
    db_session, make_virtual_product, fake_genut_repo, tmp_path
):
    """GENUT CLI 플래그는 --compile-dp-path 다(--compile-db-path 아님)."""
    vp = make_virtual_product("flag", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    events: list[tuple[str, str]] = []
    result = genut_runner.run(
        job,
        product,
        genut,
        workspace_root=str(tmp_path),
        on_event=lambda phase, level, msg: events.append((phase, msg)),
    )
    assert result.success  # fake도 --compile-dp-path를 요구하므로 성공해야 함
    cmd = next(m for p, m in events if p == "run" and m.startswith("$ "))
    assert "--compile-dp-path" in cmd
    assert "--compile-db-path" not in cmd


def test_runner_emits_git_log(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    """clone/업데이트 단계에서 프로덕트·GENUT의 git log가 job 로그로 emit된다."""
    vp = make_virtual_product("gitlog", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    events: list[tuple[str, str]] = []
    genut_runner.run(
        job,
        product,
        genut,
        workspace_root=str(tmp_path),
        on_event=lambda phase, level, msg: events.append((phase, msg)),
    )
    msgs = [m for _, m in events]
    # 프로덕트·GENUT git log 메시지를 각각 찾아 본문(커밋 subject "init")을 직접 검증
    prod_log = next(m for m in msgs if m.startswith("프로덕트 git log:"))
    genut_log = next(m for m in msgs if m.startswith("GENUT git log:"))
    assert "init" in prod_log
    assert "init" in genut_log


def test_runner_streams_events(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product("stream", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    events: list[tuple[str, str]] = []
    genut_runner.run(
        job,
        product,
        genut,
        workspace_root=str(tmp_path),
        on_event=lambda phase, level, msg: events.append((phase, msg)),
    )
    phases = {phase for phase, _ in events}
    assert "clone" in phases  # 단계 이벤트
    assert "run" in phases  # 실행 출력 스트리밍
    # GENUT의 stdout(최종 JSON 등)이 run 이벤트로 들어옴
    assert any("success" in msg for phase, msg in events if phase == "run")


def test_runner_crash_has_no_result(db_session, make_virtual_product, fake_genut_repo, tmp_path):
    vp = make_virtual_product(
        "crash", sources={"src/a.cpp": "// @genut-fn: foo\n"}, scenario={"outcome": "crash"}
    )
    product, genut, job = _setup(db_session, vp, fake_genut_repo, ["src/a.cpp"])
    result = genut_runner.run(job, product, genut, workspace_root=str(tmp_path))
    assert result.success is False
    assert result.returncode not in (0, None)
    assert result.generated_files == []
