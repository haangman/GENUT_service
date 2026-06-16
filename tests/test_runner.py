"""M7: GENUT runner (subprocess, fake GENUT + 가상 프로덕트) 테스트."""

from __future__ import annotations

import json
import os
from pathlib import Path

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

    # 이전 생성물 모사: untracked 더미 파일 추가
    keep = out / "keepme_Test.cpp"
    keep.write_text("// previously generated\n", encoding="utf-8")

    # 2차 실행(같은 code_path) → 제자리 업데이트(fetch+reset, git clean 없음)
    job2 = Job(product_id=product.id, genut_instance_id=genut.id, file_list=["src/a.cpp"])
    db_session.add(job2)
    db_session.commit()
    r2 = genut_runner.run(job2, product, genut, workspace_root=str(tmp_path))
    assert r2.success
    assert keep.is_file()  # 생성된 테스트(untracked) 보존됨


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
