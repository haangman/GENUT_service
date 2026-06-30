"""자동 실행 프로덕트 생성 + CMakeLists 스캐폴딩 테스트."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genut_service import workspace
from genut_service.services import auto_product_service


# --- 단위: 템플릿 치환 / 스캐폴딩 ----------------------------------------


def test_render_cmake_replaces_filename() -> None:
    out = auto_product_service.render_cmake(
        "set(MODULE_TEST_NAME filename_UnitTest)", "bb"
    )
    assert out == "set(MODULE_TEST_NAME bb_UnitTest)"


def test_write_scaffolding_creates_base_and_per_file(tmp_path: Path) -> None:
    base = auto_product_service.write_scaffolding(
        tmp_path, "UnitTest", ["src/aaa.c", "src/bbb.c"], auto_product_service.DEFAULT_CMAKE_TEMPLATE
    )
    assert base == tmp_path / "UnitTest"
    # 양식1: base/CMakeLists.txt
    base_txt = (tmp_path / "UnitTest" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "add_subdirectory(aaa aaa_UnitTest)" in base_txt
    assert "add_subdirectory(bbb bbb_UnitTest)" in base_txt
    # 양식2: base/<stem>/CMakeLists.txt (filename → stem)
    aaa_txt = (tmp_path / "UnitTest" / "aaa" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "set(MODULE_TEST_NAME aaa_UnitTest)" in aaa_txt
    assert (tmp_path / "UnitTest" / "bbb" / "CMakeLists.txt").is_file()


def test_write_scaffolding_regenerates_base_on_change(tmp_path: Path) -> None:
    auto_product_service.write_scaffolding(tmp_path, "UnitTest", ["a.c", "b.c"], "x")
    # 파일목록이 줄면 base/CMakeLists.txt도 그에 맞게 재생성된다
    auto_product_service.write_scaffolding(tmp_path, "UnitTest", ["a.c"], "x")
    base_txt = (tmp_path / "UnitTest" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "add_subdirectory(a a_UnitTest)" in base_txt
    assert "add_subdirectory(b b_UnitTest)" not in base_txt


# --- 통합: 자동 생성 API ------------------------------------------------


def _auto_payload(root: Path, **overrides) -> dict:
    base = {
        "name": "AA",
        "product_code": "auto-AA",
        "git_url": "https://example.com/repo.git",
        "compile_db_rel": "build",
        "out_tests_rel": "UnitTest",
        "cmake_configure_cmd": "c",
        "cmake_build_cmd": "b",
        "test_run_cmd": "r",
        "test_generation_mode": "cpp",
        "code_path": str(root),
        "auto_interval_seconds": 3600,
        "auto_file_list": ["src/aaa.c", "src/bbb.c"],
        "cmake_template": "set(MODULE_TEST_NAME filename_UnitTest)\n",
    }
    base.update(overrides)
    return base


def test_create_auto_product_api_creates_product_and_scaffolding(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "code"
    root.mkdir()
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)

    resp = client.post("/api/products/auto", json=_auto_payload(root))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["auto_run"] is True
    assert body["product_code"] == "auto-AA"
    assert body["auto_interval_seconds"] == 3600
    assert body["auto_file_list"] == ["src/aaa.c", "src/bbb.c"]

    base_txt = (root / "UnitTest" / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "add_subdirectory(aaa aaa_UnitTest)" in base_txt
    assert "add_subdirectory(bbb bbb_UnitTest)" in base_txt
    assert (root / "UnitTest" / "aaa" / "CMakeLists.txt").read_text(encoding="utf-8") == (
        "set(MODULE_TEST_NAME aaa_UnitTest)\n"
    )


def test_create_auto_product_requires_auto_prefix(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "code"
    root.mkdir()
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    resp = client.post("/api/products/auto", json=_auto_payload(root, product_code="P-1"))
    assert resp.status_code == 400
