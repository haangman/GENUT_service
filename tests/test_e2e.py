"""M7 E2E: fake GENUT + 가상 프로덕트를 실제 스케줄러로 통과시킨다."""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, Product, ProductLock
from genut_service.enums import JobStatus
from genut_service.runner import genut_runner
from genut_service.scheduler.loop import run_pending
from genut_service.services import job_service

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


def _make_product(session: Session, vp: dict) -> Product:
    product = Product(**{key: vp[key] for key in _PRODUCT_FIELDS})
    session.add(product)
    session.commit()
    return product


def _make_genut(session: Session, name: str, genut_repo: dict) -> GenutInstance:
    genut = GenutInstance(
        name=name,
        repo_url=genut_repo["repo_url"],
        run_command=genut_repo["run_command"],
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
    )
    session.add(genut)
    session.commit()
    return genut


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path))
    return tmp_path


def test_pipeline_reaches_done(
    db_session, make_virtual_product, fake_genut_repo, workspace
):
    vp = make_virtual_product("e2e-ok", mode="cpp", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product = _make_product(db_session, vp)
    _make_genut(db_session, "w1", fake_genut_repo)

    job = job_service.submit_request(db_session, product.id, ["src/a.cpp"])
    assert job is not None
    assert job.file_list == ["src/a.cpp"]

    processed = run_pending(db_session)
    assert processed == 1

    db_session.expire_all()
    done = db_session.get(Job, job.id)
    assert done.status == JobStatus.DONE.value
    assert done.result_summary is not None
    # 생성된 테스트 파일이 실제로 디스크에 존재
    assert glob.glob(str(workspace / f"job_{job.id}" / "product" / "tests" / "generated" / "test_*"))


def test_pipeline_persistent_code_path_preserves_generated(
    db_session, make_virtual_product, fake_genut_repo, workspace, tmp_path
):
    vp = make_virtual_product("e2e-cp", mode="cpp", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product = _make_product(db_session, vp)
    code_dir = tmp_path / "persist_e2e"
    product.code_path = str(code_dir)
    db_session.commit()
    _make_genut(db_session, "w-cp", fake_genut_repo)

    # 1차: 실제 스케줄러로 통과 → 영속 경로에 테스트 생성
    job1 = job_service.submit_request(db_session, product.id, ["src/a.cpp"])
    assert run_pending(db_session) == 1
    db_session.expire_all()
    assert db_session.get(Job, job1.id).status == JobStatus.DONE.value
    out = code_dir / "tests" / "generated"
    assert glob.glob(str(out / "test_*"))

    # 이전 생성물 모사(untracked) 후 2차 실행
    keep = out / "keepme_Test.cpp"
    keep.write_text("// previously generated\n", encoding="utf-8")
    job2 = job_service.submit_request(db_session, product.id, ["src/a.cpp"])
    assert run_pending(db_session) == 1
    db_session.expire_all()
    assert db_session.get(Job, job2.id).status == JobStatus.DONE.value
    assert keep.is_file()  # 제자리 업데이트 → 보존됨


def test_worker_passes_use_venv_from_settings(
    db_session, make_virtual_product, fake_genut_repo, workspace
):
    from genut_service.runner import worker

    captured: dict = {}

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return genut_runner.RunResult(
            success=True, returncode=0, stdout="", stderr="", result_summary="ok"
        )

    get_settings().genut_use_venv = True  # autouse 기본(False)을 이 테스트만 켠다

    product = _make_product(
        db_session, make_virtual_product("uv", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    )
    _make_genut(db_session, "w-uv", fake_genut_repo)
    job_service.submit_request(db_session, product.id, ["src/a.cpp"])
    # process_job에 가짜 runner를 주입해 worker가 설정값을 전달하는지 확인
    run_pending(
        db_session,
        process=lambda s, jid: worker.process_job(s, jid, runner_run=fake_run),
    )

    assert captured.get("use_venv") is True


def test_worker_marks_canceled_job(
    db_session, make_virtual_product, fake_genut_repo, workspace
):
    from genut_service.runner import process_registry, worker

    product = _make_product(
        db_session, make_virtual_product("cxl", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    )
    _make_genut(db_session, "w-cxl", fake_genut_repo)
    job = job_service.submit_request(db_session, product.id, ["src/a.cpp"])

    def fake_run(j, *_a, **_kw):
        # 실행 중 사용자가 강제 종료한 상황을 모사
        process_registry.cancel(j.id)
        return genut_runner.RunResult(
            success=False, returncode=1, stdout="", stderr="killed", result_summary=None
        )

    run_pending(db_session, process=lambda s, jid: worker.process_job(s, jid, runner_run=fake_run))
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.CANCELED.value


def test_worker_marks_canceled_even_when_run_raises(
    db_session, make_virtual_product, fake_genut_repo, workspace
):
    """취소로 서브프로세스가 죽어 예외가 나도(예: venv 단계) failed가 아니라 canceled로 끝난다."""
    from genut_service.runner import process_registry, worker

    product = _make_product(
        db_session, make_virtual_product("cxl2", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    )
    _make_genut(db_session, "w-cxl2", fake_genut_repo)
    job = job_service.submit_request(db_session, product.id, ["src/a.cpp"])

    def fake_run(j, *_a, **_kw):
        process_registry.cancel(j.id)  # 강제 종료 요청 상태에서
        raise genut_runner.VenvError(".venv 생성 실패: killed")  # venv가 죽어 예외 발생

    run_pending(db_session, process=lambda s, jid: worker.process_job(s, jid, runner_run=fake_run))
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.CANCELED.value


def test_failure_does_not_block_other_products(
    db_session, make_virtual_product, fake_genut_repo, workspace
):
    ok = _make_product(
        db_session, make_virtual_product("e2e-ok2", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    )
    bad = _make_product(
        db_session,
        make_virtual_product(
            "e2e-bad",
            sources={"src/b.cpp": "// @genut-fn: bar\n"},
            scenario={"outcome": "hard_fail"},
        ),
    )
    _make_genut(db_session, "w1", fake_genut_repo)
    _make_genut(db_session, "w2", fake_genut_repo)

    ok_job = job_service.submit_request(db_session, ok.id, ["src/a.cpp"])
    bad_job = job_service.submit_request(db_session, bad.id, ["src/b.cpp"])

    run_pending(db_session)
    db_session.expire_all()

    assert db_session.get(Job, ok_job.id).status == JobStatus.DONE.value
    assert db_session.get(Job, bad_job.id).status == JobStatus.FAILED.value
    # 두 락 모두 해제됨
    assert db_session.scalar(select(func.count()).select_from(ProductLock)) == 0


def test_job_log_download_full_and_masked(
    client, db_session, make_virtual_product, fake_genut_repo, workspace
):
    product = _make_product(
        db_session, make_virtual_product("logdl", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    )
    _make_genut(db_session, "w-log", fake_genut_repo)  # credential key = "k"
    job = job_service.submit_request(db_session, product.id, ["src/a.cpp"])
    run_pending(db_session)
    db_session.expire_all()
    assert db_session.get(Job, job.id).status == JobStatus.DONE.value

    resp = client.get(f"/api/jobs/{job.id}/log/download")
    assert resp.status_code == 200
    body = resp.text
    assert "[schedule] job 시작" in body  # 시작부터
    assert "file-list" in body  # 소스 리스트 내용
    assert "[run] $" in body  # 실제 실행 명령
    assert "DS_ASSIST_CREDENTIAL_KEY=********" in body  # 키 값 마스킹
    assert "DS_ASSIST_CREDENTIAL_KEY=k" not in body  # 실제 키 값 비노출
    assert "[collect]" in body  # 끝까지


def test_job_log_download_missing_job_404(client) -> None:
    assert client.get("/api/jobs/999999/log/download").status_code == 404
