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

    # 성공 파일에는 gtest 케이스 매크로를 담는다(calc_Test_0=2개, calc_Test_1=1개, util_Test_0=1개)
    (root / "out" / "calc" / "calc_Test_0.cpp").write_text(
        "TEST(calc, a) { EXPECT_EQ(1,1); }\nTEST_F(calcF, b) {}\n", encoding="utf-8"
    )
    (root / "out" / "calc" / "calc_Test_1.cpp").write_text("TEST(calc, c) {}\n", encoding="utf-8")
    (root / "out" / "calc" / "notes.txt").write_text("x", encoding="utf-8")
    (root / "out" / "util" / "util_Test_0.cpp").write_text("TEST(util, u) {}\n", encoding="utf-8")

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
    index = test_status_service._scan_log_index(tmp_path / "out_debug_log", tmp_path)
    assert (
        test_status_service._log_path_for(index, "calc", "calc_Test_0.cpp")
        == "out_debug_log/calc/calc_Test_0.log"
    )
    # calc_Test_1.log은 없음 → None
    assert (
        test_status_service._log_path_for(index, "calc", "calc_Test_1.cpp") is None
    )


def test_log_path_for_is_case_insensitive(tmp_path: Path) -> None:
    # 테스트 파일은 _Test, 로그 파일은 _test, stem 폴더도 대소문자 다름 → 그래도 매칭
    (tmp_path / "out_debug_log" / "Aaa").mkdir(parents=True)
    (tmp_path / "out_debug_log" / "Aaa" / "aaa_test.log").write_text("L", encoding="utf-8")
    index = test_status_service._scan_log_index(tmp_path / "out_debug_log", tmp_path)
    assert (
        test_status_service._log_path_for(index, "aaa", "aaa_Test.cpp")
        == "out_debug_log/Aaa/aaa_test.log"
    )


# --- 단위: 테스트 케이스 카운트 ------------------------------------------


def test_count_test_cases_gtest(tmp_path: Path) -> None:
    f = tmp_path / "g_Test.cpp"
    f.write_text(
        "// TEST(in, comment)\n"
        "TEST(Suite, a) { EXPECT_EQ(1, 1); }\n"
        "TEST_F(Fix, b) {}\n"
        "TEST_P(Param, c) {}\n"
        "TYPED_TEST(Typed, d) {}\n"
        "INSTANTIATE_TEST_SUITE_P(X, Param, Values(1));\n",  # TEST 미포함(부분일치 제외)
        encoding="utf-8",
    )
    # 주석의 TEST까지 포함하는 휴리스틱: TEST + TEST_F + TEST_P + TYPED_TEST + 주석 TEST = 5
    assert test_status_service._count_test_cases(f) == 5


def test_count_test_cases_kunit(tmp_path: Path) -> None:
    f = tmp_path / "k_test.c"
    f.write_text(
        "static struct kunit_case cases[] = {\n"
        "  KUNIT_CASE(test_a),\n"
        "  KUNIT_CASE(test_b),\n"
        "  KUNIT_CASE_PARAM(test_c, gen),\n"
        "  {}\n};\n",
        encoding="utf-8",
    )
    assert test_status_service._count_test_cases(f) == 3


def test_count_test_cases_caches_by_mtime(tmp_path: Path) -> None:
    f = tmp_path / "c_test.cpp"
    f.write_text("TEST(a, b) {}\n", encoding="utf-8")
    first = test_status_service._count_test_cases(f)
    assert first == 1
    # 같은 (경로,mtime,size) → 캐시 적중(동일 값)
    assert test_status_service._count_test_cases(f) == 1


def test_count_test_cases_missing_returns_none(tmp_path: Path) -> None:
    assert test_status_service._count_test_cases(tmp_path / "nope.cpp") is None


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
    # 케이스 수: 성공 파일만(calc_Test_0=2, calc_Test_1=1) → 대상 합 3, 실패 파일은 None
    cases = {t["name"]: t["case_count"] for t in calc["test_files"]}
    assert cases == {"calc_Test_0.cpp": 2, "calc_Test_1.cpp": 1}
    assert calc["case_count"] == 3
    assert calc["failed_test_files"][0]["case_count"] is None

    util = next(r for r in rows if r["path"] == "src/util.c")
    assert util["test_count"] == 1 and util["fail_count"] == 0
    assert util["case_count"] == 1


def test_build_status_matches_log_case_insensitively(tmp_path: Path) -> None:
    # 테스트 파일(aaa_Test.cpp)과 로그(aaa_test.log)의 대소문자가 달라도 로그를 찾는다.
    root = tmp_path / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "build").mkdir(parents=True)
    (root / "src" / "aaa.c").write_text("// code\n", encoding="utf-8")
    compdb = [
        {"directory": str(root / "build"), "command": "cc -c", "file": str(root / "src" / "aaa.c")}
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    (root / "out" / "aaa").mkdir(parents=True)
    (root / "out" / "aaa" / "aaa_Test.cpp").write_text("//", encoding="utf-8")  # _Test
    (root / "out_debug_log" / "aaa").mkdir(parents=True)
    (root / "out_debug_log" / "aaa" / "aaa_test.log").write_text("L", encoding="utf-8")  # _test

    class _P:
        compile_db_rel = "build"
        out_tests_rel = "out"
        exclude_globs: list[str] = []

    rows = test_status_service.build_status(root, _P())
    aaa = next(r for r in rows if r["path"] == "src/aaa.c")
    assert aaa["test_files"][0]["log_path"] == "out_debug_log/aaa/aaa_test.log"


# --- 단위: merge_status (합집합 + 출처 추적 + 실패 병합) ------------------


def test_merge_status_dedupes_and_tracks_codes() -> None:
    status = [
        {
            "name": "calc.c",
            "path": "src/calc.c",
            "test_count": 1,
            "test_files": [
                {
                    "name": "calc_Test_0.cpp",
                    "path": "out/calc/calc_Test_0.cpp",
                    "log_path": "l.log",
                    "case_count": 2,
                }
            ],
            "case_count": 2,
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
    assert merged[0]["test_files"][0]["case_count"] == 2
    assert merged[0]["case_count"] == 2  # 케이스 합도 2배 아님
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
    assert calc["case_count"] == 3  # calc_Test_0=2 + calc_Test_1=1
    assert {t["name"]: t["case_count"] for t in calc["test_files"]} == {
        "calc_Test_0.cpp": 2,
        "calc_Test_1.cpp": 1,
    }
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
    assert row["total_test_count"] == 3  # calc 2 + util 1 (테스트 파일 수)
    assert row["total_case_count"] == 4  # calc 3(2+1) + util 1 (케이스 수)
    assert row["total_fail_count"] == 1  # calc 실패 1
    assert sorted(row["product_codes"]) == ["A-1", "A-2"]


# --- 통합: 파일 내용(코드/로그) 엔드포인트 -------------------------------


def test_test_status_file_returns_code_and_log(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "existing_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1")

    code = client.get(
        "/api/test-status/file",
        params={"code": "P-1", "path": "out/calc/calc_Test_0.cpp"},
    )
    assert code.status_code == 200
    assert code.json() == {
        "path": "out/calc/calc_Test_0.cpp",
        "content": "TEST(calc, a) { EXPECT_EQ(1,1); }\nTEST_F(calcF, b) {}\n",
    }

    log = client.get(
        "/api/test-status/file",
        params={"code": "P-1", "path": "out_debug_log/calc/calc_Test_0.log"},
    )
    assert log.status_code == 200
    assert log.json()["content"] == "log0"


def test_test_status_file_unknown_code_404(client: TestClient) -> None:
    resp = client.get(
        "/api/test-status/file", params={"code": "ZZ", "path": "out/calc/x.cpp"}
    )
    assert resp.status_code == 404


def test_test_status_file_missing_file_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "existing_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1")
    resp = client.get(
        "/api/test-status/file",
        params={"code": "P-1", "path": "out/calc/nope.cpp"},
    )
    assert resp.status_code == 404


def test_test_status_file_rejects_traversal_400(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "existing_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1")
    resp = client.get(
        "/api/test-status/file",
        params={"code": "P-1", "path": "../../etc/passwd"},
    )
    assert resp.status_code == 400


def test_test_status_file_rejects_outside_allowed_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "existing_product_checkout", lambda product: root)
    _create_product(client, name="demo", code="P-1")
    # 체크아웃 안에 실재하지만 허용 루트(out/out_Fail/out_debug_log) 밖 → 404
    resp = client.get(
        "/api/test-status/file",
        params={"code": "P-1", "path": "src/calc.c"},
    )
    assert resp.status_code == 404


def test_summary_is_cached_within_ttl_and_invalidated_on_product_change(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """요약은 TTL 동안 캐시되고(스캔 1회), 프로덕트 목록이 바뀌면 즉시 무효화된다."""
    from genut_service.api import test_status as ts_api
    from genut_service.config import get_settings

    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="cached", code="C-1")

    scans: list[int] = []
    original = ts_api._scan_pairs

    def counting(products):  # noqa: ANN001
        scans.append(1)
        return original(products)

    monkeypatch.setattr(ts_api, "_scan_pairs", counting)
    get_settings().test_status_cache_ttl = 60.0  # 이 테스트만 캐시 활성(autouse가 복원)

    first = client.get("/api/test-status").json()
    second = client.get("/api/test-status").json()
    assert second == first
    assert len(scans) == 1  # TTL 안의 두 번째 요청은 캐시로 응답(재스캔 없음)

    # 프로덕트 목록 변경(신규 등록) → 지문이 달라져 즉시 재스캔
    # (_scan_pairs는 이름 그룹당 1회 — 이제 이름이 2개라 2회 추가된다)
    _create_product(client, name="cached-2", code="C-2")
    client.get("/api/test-status")
    assert len(scans) == 3


# --- 통합: 스냅샷 우선 + 폴백 ---------------------------------------------


def _refresh_snapshots_via_client(client: TestClient) -> None:
    """client 픽스처의 오버라이드된 세션으로 스냅샷을 생성한다(리프레셔 대행)."""
    from genut_service.services import test_status_snapshot_service as snap_service

    override = next(iter(client.app.dependency_overrides.values()))
    gen = override()
    session = next(gen)
    try:
        snap_service.refresh_snapshots(session)
    finally:
        gen.close()


def test_summary_prefers_snapshot_over_live_scan(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """스냅샷이 있으면 요약은 스캔 없이 스냅샷 값(+generated_at)으로 응답한다."""
    from genut_service.services import test_status_service as ts_service

    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="snap", code="S-1")
    _refresh_snapshots_via_client(client)

    scans: list[int] = []

    def no_scan(products):  # noqa: ANN001
        scans.append(1)
        return []

    monkeypatch.setattr(ts_service, "scan_group", no_scan)
    body = client.get("/api/test-status").json()
    row = next(r for r in body if r["name"] == "snap")
    assert row["total_test_count"] == 3
    assert row["generated_at"] is not None
    assert scans == []  # 스냅샷 경로 — 실시간 스캔 없음


def test_detail_prefers_snapshot_and_falls_back_without_it(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    _create_product(client, name="snap2", code="S-2")

    # 스냅샷 없음 → 폴백(실시간 스캔)으로 정상 응답 + generated_at 없음(요약 기준)
    body = client.get("/api/test-status/detail", params={"name": "snap2"}).json()
    assert [f["path"] for f in body] == ["src/calc.c", "src/util.c"]
    summary = client.get("/api/test-status").json()
    assert next(r for r in summary if r["name"] == "snap2")["generated_at"] is None

    # 스냅샷 생성 후에는 스냅샷 detail로 응답(스캔 불필요)
    _refresh_snapshots_via_client(client)
    monkeypatch.setattr(
        workspace,
        "ensure_product_checkout",
        lambda product: (_ for _ in ()).throw(AssertionError("스냅샷 경로에서 스캔 금지")),
    )
    body = client.get("/api/test-status/detail", params={"name": "snap2"}).json()
    assert [f["path"] for f in body] == ["src/calc.c", "src/util.c"]


def test_test_status_file_missing_checkout_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """체크아웃이 없으면 /file은 clone하지 않고 404를 반환한다."""
    monkeypatch.setattr(workspace, "existing_product_checkout", lambda product: None)
    _create_product(client, name="noco", code="N-1")
    resp = client.get(
        "/api/test-status/file",
        params={"code": "N-1", "path": "out/calc/calc_Test_0.cpp"},
    )
    assert resp.status_code == 404
