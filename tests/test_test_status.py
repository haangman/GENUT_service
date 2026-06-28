"""프로덕트별 테스트 현황(대상 파일 수집 + 성공/실패 테스트·로그 매칭) 테스트."""

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


# --- 픽스처: 구조 B(out / out_Fail / out_debug_log) --------------------------


def _build_out_tests(root: Path) -> None:
    """out_tests_rel="out" 기준 성공/실패/로그 폴더 구조를 만든다.

    - out/calc/calc_Test_{0,1}.cpp (성공), out/calc/notes.txt(_test 없음→제외)
    - out/util/util_Test_0.cpp (성공)
    - out_Fail/calc/calc_Test_2.cpp (실패), out_Fail/calc/extra.txt(_test 없음→제외)
    - out_debug_log/calc/calc_Test_0.log, calc_Test_2.log (calc_Test_1.log은 일부러 누락)
    """
    (root / "out" / "calc").mkdir(parents=True)
    (root / "out" / "util").mkdir(parents=True)
    (root / "out_Fail" / "calc").mkdir(parents=True)
    (root / "out_debug_log" / "calc").mkdir(parents=True)

    (root / "out" / "calc" / "calc_Test_0.cpp").write_text("//0", encoding="utf-8")
    (root / "out" / "calc" / "calc_Test_1.cpp").write_text("//1", encoding="utf-8")
    (root / "out" / "calc" / "notes.txt").write_text("x", encoding="utf-8")
    (root / "out" / "util" / "util_Test_0.cpp").write_text("//u", encoding="utf-8")

    (root / "out_Fail" / "calc" / "calc_Test_2.cpp").write_text("//2", encoding="utf-8")
    (root / "out_Fail" / "calc" / "extra.txt").write_text("x", encoding="utf-8")

    (root / "out_debug_log" / "calc" / "calc_Test_0.log").write_text("log0", encoding="utf-8")
    (root / "out_debug_log" / "calc" / "calc_Test_2.log").write_text("log2", encoding="utf-8")


# --- 단위: 스캔/형제폴더/로그 경로 ----------------------------------------


def test_scan_stem_dir_collects_only_test_files(tmp_path: Path) -> None:
    _build_out_tests(tmp_path)
    success = test_status_service._scan_stem_dir(tmp_path / "out", tmp_path)
    assert sorted(success["calc"]) == [
        "out/calc/calc_Test_0.cpp",
        "out/calc/calc_Test_1.cpp",
    ]
    assert success["util"] == ["out/util/util_Test_0.cpp"]
    # notes.txt(_test 없음)는 수집되지 않는다
    assert all("notes.txt" not in p for paths in success.values() for p in paths)


def test_scan_stem_dir_scans_fail_root(tmp_path: Path) -> None:
    _build_out_tests(tmp_path)
    failed = test_status_service._scan_stem_dir(tmp_path / "out_Fail", tmp_path)
    assert failed["calc"] == ["out_Fail/calc/calc_Test_2.cpp"]  # extra.txt 제외


def test_sibling_roots_found_case_insensitive(tmp_path: Path) -> None:
    _build_out_tests(tmp_path)
    fail_root, log_root = test_status_service._sibling_roots((tmp_path / "out").resolve())
    assert fail_root is not None and fail_root.name == "out_Fail"
    assert log_root is not None and log_root.name == "out_debug_log"


def test_sibling_roots_missing_returns_none(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    fail_root, log_root = test_status_service._sibling_roots((tmp_path / "out").resolve())
    assert fail_root is None and log_root is None


def test_log_path_for_resolves_existing_and_missing(tmp_path: Path) -> None:
    _build_out_tests(tmp_path)
    log_root = tmp_path / "out_debug_log"
    assert (
        test_status_service._log_path_for(log_root, tmp_path, "calc", "calc_Test_0.cpp")
        == "out_debug_log/calc/calc_Test_0.log"
    )
    # calc_Test_1.log은 없음 → None
    assert (
        test_status_service._log_path_for(log_root, tmp_path, "calc", "calc_Test_1.cpp")
        is None
    )


# --- 통합: build_status + API --------------------------------------------


def _make_checkout(base: Path) -> Path:
    """compile_commands.json + out/out_Fail/out_debug_log 구조를 갖춘 가짜 체크아웃."""
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
        "out_tests_rel": "out",
        "cmake_configure_cmd": "c",
        "cmake_build_cmd": "b",
        "test_run_cmd": "r",
        "test_generation_mode": "cpp",
        "exclude_globs": exclude_globs or [],
    }
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_build_status_matches_success_failed_and_logs(tmp_path: Path) -> None:
    root = _make_checkout(tmp_path)

    class _P:
        compile_db_rel = "build"
        out_tests_rel = "out"
        exclude_globs: list[str] = []

    rows = test_status_service.build_status(root, _P())
    calc = next(r for r in rows if r["path"] == "src/calc.c")
    assert calc["test_count"] == 2
    assert [t["name"] for t in calc["test_files"]] == ["calc_Test_0.cpp", "calc_Test_1.cpp"]
    logs = {t["name"]: t["log_path"] for t in calc["test_files"]}
    assert logs["calc_Test_0.cpp"] == "out_debug_log/calc/calc_Test_0.log"
    assert logs["calc_Test_1.cpp"] is None  # 로그 파일 없음
    assert calc["fail_count"] == 1
    assert calc["failed_test_files"][0]["path"] == "out_Fail/calc/calc_Test_2.cpp"
    assert calc["failed_test_files"][0]["log_path"] == "out_debug_log/calc/calc_Test_2.log"

    util = next(r for r in rows if r["path"] == "src/util.c")
    assert util["test_count"] == 1 and util["fail_count"] == 0


# --- 단위: merge_status (합집합 + 출처 추적 + 실패 병합) ------------------


def test_merge_status_dedupes_and_tracks_codes() -> None:
    status = [
        {
            "name": "calc.c",
            "path": "src/calc.c",
            "test_count": 1,
            "test_files": [
                {"name": "calc_Test_0.cpp", "path": "out/calc/calc_Test_0.cpp", "log_path": "l.log"}
            ],
            "fail_count": 0,
            "failed_test_files": [],
        }
    ]
    # 동일 데이터를 가진 두 변이 → 합집합=단일, product_codes에 둘 다
    merged = test_status_service.merge_status([("A-1", status), ("A-2", status)])
    assert len(merged) == 1
    assert merged[0]["path"] == "src/calc.c"
    assert merged[0]["product_codes"] == ["A-1", "A-2"]
    assert merged[0]["test_count"] == 1  # 2배 아님
    assert merged[0]["test_files"][0]["product_codes"] == ["A-1", "A-2"]
    assert merged[0]["test_files"][0]["log_path"] == "l.log"
    assert merged[0]["fail_count"] == 0


def test_merge_status_merges_failed_and_keeps_log_path() -> None:
    s1 = [
        {
            "name": "calc.c",
            "path": "src/calc.c",
            "test_count": 0,
            "test_files": [],
            "fail_count": 1,
            "failed_test_files": [
                {"name": "a.cpp", "path": "out_Fail/calc/a.cpp", "log_path": None}
            ],
        }
    ]
    s2 = [
        {
            "name": "calc.c",
            "path": "src/calc.c",
            "test_count": 0,
            "test_files": [],
            "fail_count": 1,
            "failed_test_files": [
                {"name": "a.cpp", "path": "out_Fail/calc/a.cpp", "log_path": "a.log"}
            ],
        }
    ]
    merged = test_status_service.merge_status([("A-1", s1), ("A-2", s2)])
    assert merged[0]["fail_count"] == 1  # 같은 path → 중복 제거
    ftf = merged[0]["failed_test_files"][0]
    assert ftf["product_codes"] == ["A-1", "A-2"]
    assert ftf["log_path"] == "a.log"  # 비-None 변이 값 채택


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
    assert calc["fail_count"] == 1
    assert calc["failed_test_files"][0]["name"] == "calc_Test_2.cpp"
    assert calc["product_codes"] == ["P-1"]
    logs = {t["name"]: t["log_path"] for t in calc["test_files"]}
    assert logs["calc_Test_0.cpp"] == "out_debug_log/calc/calc_Test_0.log"
    assert logs["calc_Test_1.cpp"] is None


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
    assert calc["fail_count"] == 1
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
    assert row["total_fail_count"] == 1  # calc 실패 1
    assert sorted(row["product_codes"]) == ["A-1", "A-2"]
