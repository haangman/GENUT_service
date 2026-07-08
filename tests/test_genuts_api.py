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


def test_user_id_round_trip_and_optional(client: TestClient, db_session: Session) -> None:
    body = client.post("/api/genuts", json=_payload("uid", ds_assist_user_id="user-42")).json()
    assert body["ds_assist_user_id"] == "user-42"
    # 미지정/빈 값 → None
    assert client.post("/api/genuts", json=_payload("uid-none")).json()["ds_assist_user_id"] is None
    assert (
        client.post("/api/genuts", json=_payload("uid-empty", ds_assist_user_id="  ")).json()[
            "ds_assist_user_id"
        ]
        is None
    )
    # 수정으로 변경
    gid = body["id"]
    client.put(f"/api/genuts/{gid}", json={"ds_assist_user_id": "user-99"})
    db_session.expire_all()
    assert db_session.get(GenutInstance, gid).ds_assist_user_id == "user-99"


def test_code_path_round_trip(client: TestClient) -> None:
    body = client.post("/api/genuts", json=_payload("g-cp", code_path="genut/checkout")).json()
    assert body["code_path"] == "genut/checkout"
    assert client.post("/api/genuts", json=_payload("g-cp2")).json()["code_path"] is None


def test_assure_repo_url_round_trip(client: TestClient) -> None:
    body = client.post(
        "/api/genuts", json=_payload("assure", assure_repo_url="https://example.com/assure.git")
    ).json()
    assert body["assure_repo_url"] == "https://example.com/assure.git"
    # 미지정/빈 값 → None
    assert client.post("/api/genuts", json=_payload("assure-none")).json()["assure_repo_url"] is None
    assert (
        client.post("/api/genuts", json=_payload("assure-empty", assure_repo_url="  ")).json()[
            "assure_repo_url"
        ]
        is None
    )


def test_llm_model_defaults_to_gpt_oss(client: TestClient) -> None:
    body = client.post("/api/genuts", json=_payload("llm-default")).json()
    assert body["llm_model"] == "gptOss"


def test_llm_model_round_trip_and_update(client: TestClient, db_session: Session) -> None:
    body = client.post("/api/genuts", json=_payload("llm", llm_model="SSCR_SE")).json()
    assert body["llm_model"] == "SSCR_SE"

    gid = body["id"]
    resp = client.put(f"/api/genuts/{gid}", json={"llm_model": "gptOss"})
    assert resp.status_code == 200
    assert resp.json()["llm_model"] == "gptOss"
    db_session.expire_all()
    assert db_session.get(GenutInstance, gid).llm_model == "gptOss"


def test_llm_model_rejects_unknown_value(client: TestClient) -> None:
    # 허용된 선택지(gptOss | SSCR_SE) 밖의 값은 422
    resp = client.post("/api/genuts", json=_payload("llm-bad", llm_model="gpt4"))
    assert resp.status_code == 422


def test_list_and_delete(client: TestClient) -> None:
    genut_id = client.post("/api/genuts", json=_payload()).json()["id"]
    listing = client.get("/api/genuts")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert client.delete(f"/api/genuts/{genut_id}").status_code == 204
    assert client.get(f"/api/genuts/{genut_id}").status_code == 404


def _add_job(db_session: Session, genut_id: int, status: str) -> int:
    """이 GENUT에 배정된 job 1건을 만든다(프로덕트 포함)."""
    from genut_service.db.models import Job, Product

    product = Product(
        name="jp", product_code=f"jp-{genut_id}-{status}", git_url="u",
        compile_db_rel="build", out_tests_rel="tests", cmake_configure_cmd="c",
        cmake_build_cmd="b", test_run_cmd="r", test_generation_mode="cpp",
    )
    db_session.add(product)
    db_session.flush()
    job = Job(product_id=product.id, genut_instance_id=genut_id, status=status)
    db_session.add(job)
    db_session.commit()
    return job.id


def test_delete_genut_keeps_finished_history_unassigned(
    client: TestClient, db_session: Session
) -> None:
    """종료 job 이력은 남기고 배정 표시만 지운 채 삭제된다 — FK로 500 나던 회귀 방지."""
    from genut_service.db.models import Job

    genut_id = client.post("/api/genuts", json=_payload("del-hist")).json()["id"]
    job_id = _add_job(db_session, genut_id, status="done")

    assert client.delete(f"/api/genuts/{genut_id}").status_code == 204
    db_session.expire_all()
    job = db_session.get(Job, job_id)
    assert job is not None  # 이력 보존
    assert job.genut_instance_id is None  # 배정 표시만 해제


def test_delete_genut_with_running_job_conflicts(
    client: TestClient, db_session: Session
) -> None:
    genut_id = client.post("/api/genuts", json=_payload("del-busy")).json()["id"]
    _add_job(db_session, genut_id, status="running")

    resp = client.delete(f"/api/genuts/{genut_id}")
    assert resp.status_code == 409
    assert "삭제할 수 없다" in resp.json()["detail"]
    assert client.get(f"/api/genuts/{genut_id}").status_code == 200
