"""auto 모드 E2E: 주기 사이클(diff/scan) → fake GENUT 실행 → 재사이클 → 변경 감지."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, Product
from genut_service.enums import JobKind, JobOrigin, JobStatus
from genut_service.scheduler import auto_tick
from genut_service.scheduler.loop import run_pending

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

# fake GENUT은 @genut-fn 마커로, auto 스캔은 실제 함수 정의 파싱으로 함수를 찾는다 —
# 둘 다 같은 함수 집합(bbb, ccc)을 보도록 마커와 정의를 함께 담는다.
AAA_SOURCE = (
    "// @genut-fn: bbb\n"
    "// @genut-fn: ccc\n"
    "int bbb(void) { return 1; }\n"
    "int ccc(void) { return 2; }\n"
)


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


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(get_settings(), "workspace_root", str(tmp_path))
    return tmp_path


def _genut_jobs(session: Session) -> list[Job]:
    return list(
        session.scalars(
            select(Job).where(Job.kind == JobKind.GENUT.value).order_by(Job.id)
        )
    )


def _force_due(session: Session, product: Product) -> None:
    product.last_auto_run_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.commit()


def test_auto_mode_end_to_end(
    db_session: Session, make_virtual_product, fake_genut_repo, workspace, tmp_path
) -> None:
    # fake GENUT이 실 GENUT 디스크 구조(<out>/<stem>/<함수>_Test.cpp)로 생성하도록 설정
    vp = make_virtual_product(
        "auto-e2e",
        mode="cpp",
        sources={"src/aaa.c": AAA_SOURCE},
        scenario={"out_layout": "stem_dirs"},
    )
    product = Product(**{key: vp[key] for key in _PRODUCT_FIELDS})
    product.out_tests_rel = "unittests"
    product.code_path = str(tmp_path / "auto_code")
    product.auto_run = True
    product.auto_interval_seconds = 60
    product.auto_file_list = ["src/aaa.c"]
    db_session.add(product)
    db_session.add(
        GenutInstance(
            name="w-auto",
            repo_url=fake_genut_repo["repo_url"],
            run_command=fake_genut_repo["run_command"],
            ds_assist_credential_key="k",
            ds_assist_send_system_name="s",
        )
    )
    db_session.commit()

    # ── 사이클 1: 최초 — diff는 기준 커밋만 기록, scan은 테스트 전무 → 파일 단위 job
    assert auto_tick.run_auto_pending(db_session) == 2
    db_session.expire_all()
    assert product.last_scanned_commit is not None
    jobs = _genut_jobs(db_session)
    assert [(j.file_list, j.function_name, j.origin) for j in jobs] == [
        (["src/aaa.c"], None, JobOrigin.AUTO.value)
    ]

    # ── GENUT 실행: unittests/aaa/{bbb,ccc}_Test.cpp 생성
    assert run_pending(db_session) == 1
    db_session.expire_all()
    assert jobs[0].status == JobStatus.DONE.value
    out_dir = Path(product.code_path) / "unittests" / "aaa"
    assert (out_dir / "bbb_Test.cpp").is_file()
    assert (out_dir / "ccc_Test.cpp").is_file()

    # ── 사이클 2: 모든 함수가 커버됨 → 새 GENUT job 없음
    _force_due(db_session, product)
    auto_tick.run_auto_pending(db_session)
    assert len(_genut_jobs(db_session)) == 1  # 그대로

    # ── 원격(origin)에서 ccc 본문 수정 → 사이클 3: 변경 감지가 ccc만 큐잉
    origin: Path = vp["repo"]
    (origin / "src" / "aaa.c").write_text(
        AAA_SOURCE.replace("return 2;", "return 22;"), encoding="utf-8"
    )
    _git(["commit", "-am", "change ccc"], origin)

    _force_due(db_session, product)
    auto_tick.run_auto_pending(db_session)
    db_session.expire_all()
    new_jobs = [j for j in _genut_jobs(db_session) if j.status == JobStatus.QUEUED.value]
    assert [(j.file_list, j.function_name) for j in new_jobs] == [(["src/aaa.c"], "ccc")]

    # 변경 감지 job까지 실행하면 다시 모두 커버 상태가 된다
    assert run_pending(db_session) == 1
    db_session.expire_all()
    assert all(j.status == JobStatus.DONE.value for j in _genut_jobs(db_session))

    # ── 사이클 4: 다시 조용한 상태 — 새 job 없음 (기준 커밋도 최신으로 전진했음)
    _force_due(db_session, product)
    auto_tick.run_auto_pending(db_session)
    assert len(_genut_jobs(db_session)) == 2
    prep_jobs = list(
        db_session.scalars(
            select(Job).where(Job.kind != JobKind.GENUT.value).order_by(Job.id)
        )
    )
    # 사이클 4개 × (diff+scan) = 준비 job 8개, 전부 정상 종료
    assert len(prep_jobs) == 8
    assert all(j.status == JobStatus.DONE.value for j in prep_jobs)


def test_auto_generated_job_runs_with_function_scope(
    db_session: Session, make_virtual_product, fake_genut_repo, workspace, tmp_path
) -> None:
    """함수 단위 auto job이 GENUT에 --function-name으로 전달되어 그 함수만 생성한다."""
    vp = make_virtual_product(
        "auto-fn",
        mode="cpp",
        sources={"src/aaa.c": AAA_SOURCE},
        scenario={"out_layout": "stem_dirs"},
    )
    product = Product(**{key: vp[key] for key in _PRODUCT_FIELDS})
    product.out_tests_rel = "unittests"
    product.code_path = str(tmp_path / "auto_fn_code")
    product.auto_run = True
    product.auto_interval_seconds = 60
    product.auto_file_list = ["src/aaa.c"]
    db_session.add(product)
    db_session.add(
        GenutInstance(
            name="w-auto-fn",
            repo_url=fake_genut_repo["repo_url"],
            run_command=fake_genut_repo["run_command"],
            ds_assist_credential_key="k",
            ds_assist_send_system_name="s",
        )
    )
    db_session.commit()

    # bbb만 커버된 상태를 만든다 → scan이 ccc 함수 단위 job을 큐잉
    out_dir = Path(product.code_path)
    # 먼저 체크아웃이 생기도록 사이클 1 실행 전에 코드가 없으므로, 사이클로 만든 파일 단위
    # job 대신 "bbb 커버" 상태를 직접 구성한다: 체크아웃 생성 → 테스트 파일 배치.
    from genut_service import workspace as ws

    root = ws.ensure_product_checkout(product)
    (root / "unittests" / "aaa").mkdir(parents=True, exist_ok=True)
    (root / "unittests" / "aaa" / "bbb_Test.cpp").write_text("// covered\n", encoding="utf-8")

    assert auto_tick.run_auto_pending(db_session) == 2
    jobs = _genut_jobs(db_session)
    assert [(j.function_name) for j in jobs] == ["ccc"]

    # 실행: fake GENUT이 --function-name=ccc만 생성
    assert run_pending(db_session) == 1
    db_session.expire_all()
    assert jobs[0].status == JobStatus.DONE.value
    assert (root / "unittests" / "aaa" / "ccc_Test.cpp").is_file()
    # bbb는 이번 실행에서 다시 만들지 않았다(기존 파일 그대로)
    assert (root / "unittests" / "aaa" / "bbb_Test.cpp").read_text(encoding="utf-8") == "// covered\n"