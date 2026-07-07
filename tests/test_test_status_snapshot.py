"""테스트 현황 스냅샷 서비스(refresh/load) 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
# 별칭 import: 이름이 Test로 시작해 pytest가 테스트 클래스로 오인 수집하는 것을 막는다
from genut_service.db.models import Product
from genut_service.db.models import TestStatusSnapshot as StatusSnapshot
from genut_service.services import test_status_snapshot_service as snap

from tests.test_test_status import _make_checkout


def _add_product(
    session: Session, name: str = "demo", code: str = "P-1"
) -> Product:
    product = Product(
        name=name,
        product_code=code,
        git_url="https://example.com/repo.git",
        git_ref="main",
        compile_db_rel="build",
        out_tests_rel="out",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
        exclude_globs=[],
    )
    session.add(product)
    session.commit()
    return product


def test_refresh_creates_snapshot_with_summary_and_detail(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _add_product(db_session, name="demo", code="P-1")

    assert snap.refresh_snapshots(db_session) == 1

    row = db_session.get(StatusSnapshot, "demo")
    assert row is not None
    assert row.summary["name"] == "demo"
    assert row.summary["product_codes"] == ["P-1"]
    assert row.summary["target_file_count"] == 2  # calc.c, util.c (build/gen.c 제외)
    assert row.summary["total_test_count"] == 3  # calc 2 + util 1
    assert row.summary["total_case_count"] == 4  # calc 3(2+1) + util 1
    assert row.summary["total_fail_count"] == 1
    assert row.generated_at is not None
    # detail은 merge_status 결과 그대로(파일별 성공/실패 테스트 파일 포함)
    calc = next(r for r in row.detail if r["path"] == "src/calc.c")
    assert calc["test_count"] == 2 and calc["fail_count"] == 1
    assert calc["product_codes"] == ["P-1"]


def test_refresh_merges_same_name_variants(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _add_product(db_session, name="A", code="A-1")
    _add_product(db_session, name="A", code="A-2")

    assert snap.refresh_snapshots(db_session) == 1  # 이름 1개 → 스냅샷 1행

    row = db_session.get(StatusSnapshot, "A")
    assert row.summary["product_codes"] == ["A-1", "A-2"]
    assert row.summary["target_file_count"] == 2  # 합집합(2배 아님)


def test_refresh_updates_and_deletes_stale_names(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product = _add_product(db_session, name="old", code="O-1")
    snap.refresh_snapshots(db_session)
    assert db_session.get(StatusSnapshot, "old") is not None
    first_fingerprint = db_session.get(StatusSnapshot, "old").fingerprint

    # 이름 변경 → 기존 이름 스냅샷은 삭제되고 새 이름으로 생성된다
    product = db_session.get(Product, product.id)
    product.name = "new"
    db_session.commit()
    snap.refresh_snapshots(db_session)
    assert db_session.get(StatusSnapshot, "old") is None
    new_row = db_session.get(StatusSnapshot, "new")
    assert new_row is not None
    assert new_row.fingerprint != first_fingerprint  # updated_at 변화가 지문에 반영


def test_refresh_with_no_products_clears_all(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product = _add_product(db_session, name="gone", code="G-1")
    snap.refresh_snapshots(db_session)
    db_session.delete(db_session.get(Product, product.id))
    db_session.commit()

    assert snap.refresh_snapshots(db_session) == 0
    assert db_session.scalars(select(StatusSnapshot)).all() == []


def test_refresh_isolates_scan_failure_per_product(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 체크아웃 실패(예: clone 불가) → 빈 결과로 격리되어 스냅샷은 생성된다
    def boom(product):  # noqa: ANN001
        raise OSError("clone failed")

    monkeypatch.setattr(workspace, "ensure_product_checkout", boom)
    _add_product(db_session, name="broken", code="B-1")

    assert snap.refresh_snapshots(db_session) == 1
    row = db_session.get(StatusSnapshot, "broken")
    assert row.summary["target_file_count"] == 0
    assert row.detail == []


def test_load_summaries_and_detail(
    db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _add_product(db_session, name="demo", code="P-1")
    snap.refresh_snapshots(db_session)

    summaries = snap.load_summaries(db_session)
    assert set(summaries) == {"demo"}
    summary, generated_at = summaries["demo"]
    assert summary["total_test_count"] == 3
    assert generated_at is not None

    detail = snap.load_detail(db_session, "demo")
    assert detail is not None
    assert [r["path"] for r in detail] == ["src/calc.c", "src/util.c"]
    assert snap.load_detail(db_session, "nope") is None
