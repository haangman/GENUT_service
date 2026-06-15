"""M6: GENUT 인스턴스 등록 API 테스트."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance


def _payload(name: str = "genut-1", **overrides) -> dict:
    base = {
        "name": name,
        "repo_url": "https://example.com/genut.git",
        "ds_assist_credential_key": "super-secret",
        "ds_assist_send_system_name": "sys-A",
    }
    base.update(overrides)
    return base


def test_create_genut_hides_secret_and_sets_defaults(client: TestClient) -> None:
    resp = client.post("/api/genuts", json=_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "ds_assist_credential_key" not in body
    assert body["max_attempts"] == 10
    assert body["run_command"] == "python -m genut"
    assert body["worker_status"] == "idle"
    assert body["enabled"] is True


def test_secret_is_persisted(client: TestClient, db_session: Session) -> None:
    genut_id = client.post("/api/genuts", json=_payload()).json()["id"]
    stored = db_session.get(GenutInstance, genut_id)
    assert stored is not None
    assert stored.ds_assist_credential_key == "super-secret"


def test_update_without_key_keeps_existing(client: TestClient, db_session: Session) -> None:
    genut_id = client.post("/api/genuts", json=_payload()).json()["id"]
    resp = client.put(f"/api/genuts/{genut_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    db_session.expire_all()
    assert db_session.get(GenutInstance, genut_id).ds_assist_credential_key == "super-secret"


def test_update_with_key_changes_it(client: TestClient, db_session: Session) -> None:
    genut_id = client.post("/api/genuts", json=_payload()).json()["id"]
    client.put(f"/api/genuts/{genut_id}", json={"ds_assist_credential_key": "new-key"})
    db_session.expire_all()
    assert db_session.get(GenutInstance, genut_id).ds_assist_credential_key == "new-key"


def test_duplicate_name_conflict(client: TestClient) -> None:
    assert client.post("/api/genuts", json=_payload("dup")).status_code == 201
    assert client.post("/api/genuts", json=_payload("dup")).status_code == 409


def test_list_and_delete(client: TestClient) -> None:
    genut_id = client.post("/api/genuts", json=_payload()).json()["id"]
    listing = client.get("/api/genuts")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert client.delete(f"/api/genuts/{genut_id}").status_code == 204
    assert client.get(f"/api/genuts/{genut_id}").status_code == 404
