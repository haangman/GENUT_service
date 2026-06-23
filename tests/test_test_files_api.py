"""프로덕트별 테스트 파일 등록/다운로드 API·서비스 테스트."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genut_service import workspace
from genut_service.services import test_file_service


def _create_product(client: TestClient, name: str = "demo") -> int:
    payload = {
        "name": name,
        "product_code": f"{name}-1",
        "git_url": "https://example.com/repo.git",
        "compile_db_rel": "build",
        "out_tests_rel": "tests/generated",
        "cmake_configure_cmd": "cmake -S . -B build",
        "cmake_build_cmd": "cmake --build build",
        "test_run_cmd": "ctest --test-dir build",
        "test_generation_mode": "cpp",
    }
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201
    return resp.json()["id"]


def _build_tests_dir(base: Path) -> Path:
    """가짜 프로덕트 체크아웃: tests/generated 아래에 테스트 파일들."""
    root = base / "checkout"
    gen = root / "tests" / "generated"
    gen.mkdir(parents=True)
    (gen / "test_add_pos.cpp").write_text("// pos\n", encoding="utf-8")
    (gen / "test_add_neg.cpp").write_text("// neg\n", encoding="utf-8")
    (gen / "result.json").write_text("{}", encoding="utf-8")
    (root / "secret.txt").write_text("nope", encoding="utf-8")
    return root


# --- 등록/조회/삭제 -------------------------------------------------------


def test_add_then_list_reflects(client: TestClient) -> None:
    resp = client.post(
        "/api/test-files",
        json={"product_name": "AA", "rel_paths": ["tests/generated/test_a.cpp"]},
    )
    assert resp.status_code == 201
    assert [r["rel_path"] for r in resp.json()] == ["tests/generated/test_a.cpp"]

    listed = client.get("/api/test-files", params={"product_name": "AA"})
    assert listed.status_code == 200
    assert [r["rel_path"] for r in listed.json()] == ["tests/generated/test_a.cpp"]


def test_add_dedupes_existing(client: TestClient) -> None:
    client.post(
        "/api/test-files",
        json={"product_name": "AA", "rel_paths": ["tests/generated/test_a.cpp"]},
    )
    # 같은 경로를 다시 등록해도 중복되지 않는다
    again = client.post(
        "/api/test-files",
        json={
            "product_name": "AA",
            "rel_paths": ["tests/generated/test_a.cpp", "tests/generated/test_b.cpp"],
        },
    )
    assert again.status_code == 201
    assert sorted(r["rel_path"] for r in again.json()) == [
        "tests/generated/test_a.cpp",
        "tests/generated/test_b.cpp",
    ]


def test_add_is_scoped_by_product_name(client: TestClient) -> None:
    client.post("/api/test-files", json={"product_name": "AA", "rel_paths": ["a.cpp"]})
    client.post("/api/test-files", json={"product_name": "BB", "rel_paths": ["b.cpp"]})
    aa = client.get("/api/test-files", params={"product_name": "AA"}).json()
    bb = client.get("/api/test-files", params={"product_name": "BB"}).json()
    assert [r["rel_path"] for r in aa] == ["a.cpp"]
    assert [r["rel_path"] for r in bb] == ["b.cpp"]


def test_remove(client: TestClient) -> None:
    client.post(
        "/api/test-files",
        json={"product_name": "AA", "rel_paths": ["a.cpp", "b.cpp"]},
    )
    removed = client.request(
        "DELETE",
        "/api/test-files",
        json={"product_name": "AA", "rel_paths": ["a.cpp"]},
    )
    assert removed.status_code == 200
    assert removed.json() == {"removed": 1}
    remaining = client.get("/api/test-files", params={"product_name": "AA"}).json()
    assert [r["rel_path"] for r in remaining] == ["b.cpp"]


# --- 다운로드(zip) --------------------------------------------------------


def test_download_zips_selected_files(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _build_tests_dir(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client)

    resp = client.post(
        "/api/test-files/download",
        json={
            "product_id": product_id,
            "rel_paths": [
                "tests/generated/test_add_pos.cpp",
                "tests/generated/test_add_neg.cpp",
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert sorted(archive.namelist()) == [
            "tests/generated/test_add_neg.cpp",
            "tests/generated/test_add_pos.cpp",
        ]
        assert archive.read("tests/generated/test_add_pos.cpp").startswith(b"// pos")


def test_download_skips_missing_and_traversal(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _build_tests_dir(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client)

    resp = client.post(
        "/api/test-files/download",
        json={
            "product_id": product_id,
            "rel_paths": [
                "tests/generated/test_add_pos.cpp",  # 유효
                "tests/generated/nope.cpp",  # 없음 → skip
                "../outside.cpp",  # 트래버설 → skip
            ],
        },
    )
    assert resp.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        assert archive.namelist() == ["tests/generated/test_add_pos.cpp"]


def test_download_all_invalid_returns_404(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _build_tests_dir(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client)

    resp = client.post(
        "/api/test-files/download",
        json={"product_id": product_id, "rel_paths": ["does/not/exist.cpp"]},
    )
    assert resp.status_code == 404


def test_download_missing_product_404(client: TestClient) -> None:
    resp = client.post(
        "/api/test-files/download",
        json={"product_id": 9999, "rel_paths": ["a.cpp"]},
    )
    assert resp.status_code == 404


# --- 서비스 단위: build_zip 경계 ------------------------------------------


def test_build_zip_boundary(tmp_path: Path) -> None:
    root = _build_tests_dir(tmp_path)
    # 유효 1개 + 트래버설 + 없음 → 유효만 포함
    data = test_file_service.build_zip(
        root,
        ["tests/generated/test_add_pos.cpp", "../secret.txt", "tests/generated/x.cpp"],
    )
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == ["tests/generated/test_add_pos.cpp"]
    # 유효 0개 → 빈 바이트
    assert test_file_service.build_zip(root, ["../secret.txt"]) == b""
