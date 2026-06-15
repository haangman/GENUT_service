"""M3: 파일트리 탐색 및 compile_commands.json 포함 검사 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genut_service import workspace
from genut_service.services import compile_db_service, filetree_service


def _build_checkout(base: Path) -> Path:
    root = base / "checkout"
    (root / "src").mkdir(parents=True)
    (root / "include").mkdir(parents=True)
    (root / "build").mkdir(parents=True)
    for name in ("a.cpp", "b.cpp", "c.cpp"):
        (root / "src" / name).write_text("// code\n", encoding="utf-8")
    (root / "include" / "h.hpp").write_text("#pragma once\n", encoding="utf-8")
    compdb = [
        {"directory": str(root / "build"), "command": "c++ -c", "file": str(root / "src" / "a.cpp")},
        {"directory": str(root / "build"), "command": "c++ -c", "file": str(root / "src" / "c.cpp")},
    ]
    (root / "build" / "compile_commands.json").write_text(json.dumps(compdb), encoding="utf-8")
    return root


def test_list_dir_root_lists_dirs_first(tmp_path: Path) -> None:
    root = _build_checkout(tmp_path)
    entries = filetree_service.list_dir(root, "")
    assert [e["name"] for e in entries] == ["build", "include", "src"]
    assert all(e["type"] == "dir" for e in entries)


def test_list_dir_lists_source_files(tmp_path: Path) -> None:
    root = _build_checkout(tmp_path)
    entries = filetree_service.list_dir(root, "src")
    assert [e["name"] for e in entries] == ["a.cpp", "b.cpp", "c.cpp"]
    assert {e["path"] for e in entries} == {"src/a.cpp", "src/b.cpp", "src/c.cpp"}
    assert all(e["type"] == "file" for e in entries)


def test_list_dir_rejects_bad_paths(tmp_path: Path) -> None:
    root = _build_checkout(tmp_path)
    with pytest.raises(ValueError):
        filetree_service.list_dir(root, "..")
    with pytest.raises(FileNotFoundError):
        filetree_service.list_dir(root, "nope")


def test_split_inclusion_handles_bom_compdb(tmp_path: Path) -> None:
    # Windows 툴이 생성한 compile_commands.json은 BOM이 붙을 수 있다
    root = _build_checkout(tmp_path)
    db = root / "build" / "compile_commands.json"
    db.write_text("﻿" + db.read_text(encoding="utf-8"), encoding="utf-8")
    included, excluded = compile_db_service.split_inclusion(root, "build", ["src/a.cpp"])
    assert included == ["src/a.cpp"]
    assert excluded == []


def test_split_inclusion_partial_compdb(tmp_path: Path) -> None:
    root = _build_checkout(tmp_path)
    included, excluded = compile_db_service.split_inclusion(
        root, "build", ["src/a.cpp", "src/b.cpp", "src/c.cpp"]
    )
    assert included == ["src/a.cpp", "src/c.cpp"]
    assert excluded == ["src/b.cpp"]


def _create_product(client: TestClient) -> int:
    payload = {
        "name": "demo",
        "product_code": "P-1",
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


def test_tree_and_compile_check_api(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _build_checkout(tmp_path)
    monkeypatch.setattr(workspace, "ensure_product_checkout", lambda product: root)
    product_id = _create_product(client)

    tree = client.get(f"/api/products/{product_id}/tree", params={"path": "src"})
    assert tree.status_code == 200
    names = [e["name"] for e in tree.json()["entries"]]
    assert names == ["a.cpp", "b.cpp", "c.cpp"]

    check = client.post(
        f"/api/products/{product_id}/compile-check",
        json={"files": ["src/a.cpp", "src/b.cpp", "src/c.cpp"]},
    )
    assert check.status_code == 200
    body = check.json()
    assert body["included"] == ["src/a.cpp", "src/c.cpp"]
    assert body["excluded"] == ["src/b.cpp"]


def test_tree_for_missing_product_404(client: TestClient) -> None:
    assert client.get("/api/products/9999/tree").status_code == 404
