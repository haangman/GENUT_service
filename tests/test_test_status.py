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


def _create_product(
    client: TestClient,
    name: str = "demo",
    code: str = "P-1",
    exclude_globs: list[str] | None = None,
) -> int:
    payload = {
        "name": name,
        "product_code": code,
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


# --- 단위: merge_status (합집합 + 출처 추적) ------------------------------


def test_merge_status_dedupes_and_tracks_codes() -> None:
    status = [
        {
            "name": "calc.c",
            "path": "src/calc.c",
            "test_count": 1,
            "test_files": [{"name": "calc_Test_0.cpp", "path": "t/calc_Test_0.cpp"}],
        }
    ]
    # 동일 데이터를 가진 두 변이 → 합집합=단일, product_codes에 둘 다
    merged = test_status_service.merge_status([("A-1", status), ("A-2", status)])
    assert len(merged) == 1
    assert merged[0]["path"] == "src/calc.c"
    assert merged[0]["product_codes"] == ["A-1", "A-2"]
    assert merged[0]["test_count"] == 1  # 2배 아님
    assert merged[0]["test_files"][0]["product_codes"] == ["A-1", "A-2"]


def test_merge_status_unions_distinct_test_files() -> None:
    s1 = [{"name": "calc.c", "path": "src/calc.c", "test_count": 1,
           "test_files": [{"name": "a.cpp", "path": "t/a.cpp"}]}]
    s2 = [{"name": "calc.c", "path": "src/calc.c", "test_count": 1,
           "test_files": [{"name": "b.cpp", "path": "t/b.cpp"}]}]
    merged = test_status_service.merge_status([("A-1", s1), ("A-2", s2)])
    assert merged[0]["test_count"] == 2  # 서로 다른 테스트 → 합쳐서 2
    by_path = {tf["path"]: tf["product_codes"] for tf in merged[0]["test_files"]}
    assert by_path == {"t/a.cpp": ["A-1"], "t/b.cpp": ["A-2"]}


# --- 통합: 이름 기반 상세/요약 API ---------------------------------------


def test_test_status_detail_by_name(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1")

    resp = client.get("/api/test-status/detail", params={"name": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert [f["path"] for f in body] == ["src/calc.c", "src/util.c"]  # build/gen.c 제외
    calc = next(f for f in body if f["path"] == "src/calc.c")
    assert calc["test_count"] == 2
    assert calc["product_codes"] == ["P-1"]
    assert all(t["product_codes"] == ["P-1"] for t in calc["test_files"])


def test_test_status_detail_groups_same_name_union(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    # 같은 이름 'A'의 두 변이(A-1, A-2) → 같은 체크아웃 공유 → 합집합(2배 아님)
    _create_product(client, name="A", code="A-1")
    _create_product(client, name="A", code="A-2")

    body = client.get("/api/test-status/detail", params={"name": "A"}).json()
    assert [f["path"] for f in body] == ["src/calc.c", "src/util.c"]
    calc = next(f for f in body if f["path"] == "src/calc.c")
    assert calc["test_count"] == 2  # 중복 제거(2배 아님)
    assert calc["product_codes"] == ["A-1", "A-2"]  # 두 변이 모두 출처
    assert all(sorted(t["product_codes"]) == ["A-1", "A-2"] for t in calc["test_files"])


def test_test_status_detail_applies_exclude_globs(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1", exclude_globs=["*util*"])

    body = client.get("/api/test-status/detail", params={"name": "demo"}).json()
    assert [f["path"] for f in body] == ["src/calc.c"]  # util은 글롭으로 제외


def test_test_status_detail_missing_name_404(client: TestClient) -> None:
    assert client.get("/api/test-status/detail", params={"name": "nope"}).status_code == 404


def test_test_status_summary_groups_by_name(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="A", code="A-1")
    _create_product(client, name="A", code="A-2")

    body = client.get("/api/test-status").json()
    rows = [r for r in body if r["name"] == "A"]
    assert len(rows) == 1  # 이름 1행으로 합산
    row = rows[0]
    assert row["target_file_count"] == 2  # calc.c, util.c (2배 아님)
    assert row["total_test_count"] == 3  # calc 2 + util 1
    assert sorted(row["product_codes"]) == ["A-1", "A-2"]
