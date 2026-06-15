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
