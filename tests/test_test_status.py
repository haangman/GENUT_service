"""프로덕트별 테스트 현황(대상 파일 수집 + 생성 테스트 매칭) 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genut_service import workspace
from genut_service.services import test_status_service


# --- 단위: target_files 필터 ---------------------------------------------


def test_target_files_excludes_build_and_test_and_globs() -> None:
    rels = [
        "src/calc.c",
        "src/util.c",
        "build/gen.c",  # build 폴더 하위 → 제외
        "Build/x.c",  # Build 폴더 하위 → 제외
        "tests/foo.c",  # test 포함 폴더 → 제외
        "src/UnitTest/bar.c",  # Test 포함 폴더 → 제외
        "src/legacy/old.c",
    ]
    # 사용자 글롭으로 legacy 제외
    result = test_status_service.target_files(rels, ["*legacy*"])
    assert result == ["src/calc.c", "src/util.c"]


# --- 단위: scan_out_tests 매칭 -------------------------------------------


def _build_out_tests(base: Path) -> Path:
    out = base / "tests" / "generated"
    (out / "Scenario1" / "calc").mkdir(parents=True)
    (out / "Scenario1" / "util").mkdir(parents=True)
    (out / "Edge_Fail" / "calc").mkdir(parents=True)
    (out / "Scenario1" / "calc" / "calc_Test_0.cpp").write_text("//", encoding="utf-8")
    (out / "Scenario1" / "calc" / "calc_Test_1.cpp").write_text("//", encoding="utf-8")
    (out / "Scenario1" / "calc" / "notes.txt").write_text("x", encoding="utf-8")  # _test 없음
    (out / "Scenario1" / "util" / "util_Test_0.cpp").write_text("//", encoding="utf-8")
    (out / "Edge_Fail" / "calc" / "calc_Test_x.cpp").write_text("//", encoding="utf-8")  # 부모 _Fail
    return out


def test_scan_out_tests_skips_fail_parent_and_non_test_files(tmp_path: Path) -> None:
    out = _build_out_tests(tmp_path)
    mapping = test_status_service.scan_out_tests(out)
    assert sorted(mapping["calc"]) == [
        "Scenario1/calc/calc_Test_0.cpp",
        "Scenario1/calc/calc_Test_1.cpp",
    ]
    assert mapping["util"] == ["Scenario1/util/util_Test_0.cpp"]
    # Edge_Fail(부모 _Fail) 하위 calc 테스트는 포함되지 않는다
    assert all("Edge_Fail" not in p for paths in mapping.values() for p in paths)


# --- 통합: build_status + API --------------------------------------------


def _make_checkout(base: Path) -> Path:
    """compile_commands.json + out_tests 구조를 갖춘 가짜 체크아웃."""
    root = base / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "build").mkdir(parents=True)
    for rel in ("src/calc.c", "src/util.c", "build/gen.c"):
        (root / rel).write_text("// code\n", encoding="utf-8")
    compdb = [
        {"directory": str(root / "build"), "command": "cc -c", "file": str(root / rel)}
        for rel in ("src/calc.c", "src/util.c", "build/gen.c")
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    _build_out_tests(root)
    return root


def _create_product(client: TestClient, exclude_globs: list[str] | None = None) -> int:
    payload = {
        "name": "demo",
        "product_code": "P-1",
        "git_url": "https://example.com/repo.git",
        "compile_db_rel": "build",
        "out_tests_rel": "tests/generated",
        "cmake_configure_cmd": "c",
        "cmake_build_cmd": "b",
        "test_run_cmd": "r",
        "test_generation_mode": "cpp",
        "exclude_globs": exclude_globs or [],
    }
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_test_status_api_lists_targets_with_counts(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client)

    resp = client.get(f"/api/products/{product_id}/test-status")
    assert resp.status_code == 200
    body = resp.json()
    # build/gen.c는 제외, src/calc.c·src/util.c만 대상 (path 오름차순)
    assert [f["path"] for f in body] == ["src/calc.c", "src/util.c"]

    calc = next(f for f in body if f["path"] == "src/calc.c")
    assert calc["name"] == "calc.c"
    assert calc["test_count"] == 2
    assert sorted(t["path"] for t in calc["test_files"]) == [
        "tests/generated/Scenario1/calc/calc_Test_0.cpp",
        "tests/generated/Scenario1/calc/calc_Test_1.cpp",
    ]
    util = next(f for f in body if f["path"] == "src/util.c")
    assert util["test_count"] == 1


def test_test_status_api_applies_exclude_globs(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client, exclude_globs=["*util*"])

    body = client.get(f"/api/products/{product_id}/test-status").json()
    assert [f["path"] for f in body] == ["src/calc.c"]  # util은 글롭으로 제외


def test_test_status_missing_product_404(client: TestClient) -> None:
    assert client.get("/api/products/9999/test-status").status_code == 404


def test_test_status_summary_lists_per_product_counts(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    pid = _create_product(client)

    body = client.get("/api/test-status").json()
    row = next(r for r in body if r["product_id"] == pid)
    # 대상 파일 2개(calc.c, util.c), 총 테스트 3개(calc 2 + util 1)
    assert row["target_file_count"] == 2
    assert row["total_test_count"] == 3
    assert row["name"] == "demo"
