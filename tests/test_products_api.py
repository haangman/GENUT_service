"""M2: 프로덕트 등록 API 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _payload(name: str = "demo", **overrides) -> dict:
    base = {
        "name": name,
        "product_code": "P-1",
        "git_url": "https://example.com/repo.git",
        "compile_db_rel": "build",
        "out_tests_rel": "tests/generated",
        "cmake_configure_cmd": "cmake -S . -B build",
        "cmake_build_cmd": "cmake --build build",
        "test_run_cmd": "ctest --test-dir build",
        "test_generation_mode": "cpp",
    }
    base.update(overrides)
    return base


def test_create_and_get_product(client: TestClient) -> None:
    payload = _payload(
        patches=[
            {"name": "second", "content": "diff-2", "order_index": 1},
            {"name": "first", "content": "diff-1", "order_index": 0},
        ]
    )
    resp = client.post("/api/products", json=payload)
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["id"] > 0
    assert created["test_generation_mode"] == "cpp"
    assert [p["order_index"] for p in created["patches"]] == [0, 1]

    got = client.get(f"/api/products/{created['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "demo"


def test_paths_are_normalized(client: TestClient) -> None:
    resp = client.post(
        "/api/products", json=_payload(compile_db_rel="build\\out\\", out_tests_rel="/tests/gen")
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["compile_db_rel"] == "build/out"
    assert body["out_tests_rel"] == "tests/gen"


def test_parent_path_is_rejected(client: TestClient) -> None:
    resp = client.post("/api/products", json=_payload(compile_db_rel="../secret"))
    assert resp.status_code == 422


def test_duplicate_name_conflict(client: TestClient) -> None:
    assert client.post("/api/products", json=_payload("dup")).status_code == 201
    resp = client.post("/api/products", json=_payload("dup"))
    assert resp.status_code == 409


def test_list_pagination(client: TestClient) -> None:
    for i in range(3):
        client.post("/api/products", json=_payload(f"p{i}"))
    resp = client.get("/api/products", params={"page": 1, "page_size": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_update_product_and_patches(client: TestClient) -> None:
    created = client.post("/api/products", json=_payload()).json()
    resp = client.put(
        f"/api/products/{created['id']}",
        json={"git_ref": "develop", "patches": [{"name": "p", "content": "d", "order_index": 0}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_ref"] == "develop"
    assert len(body["patches"]) == 1


def test_delete_product(client: TestClient) -> None:
    created = client.post("/api/products", json=_payload()).json()
    assert client.delete(f"/api/products/{created['id']}").status_code == 204
    assert client.get(f"/api/products/{created['id']}").status_code == 404


def test_get_missing_returns_404(client: TestClient) -> None:
    assert client.get("/api/products/9999").status_code == 404
