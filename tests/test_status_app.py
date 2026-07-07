"""독립 테스트 현황 서버(create_status_app) 테스트."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from genut_service.api.deps import get_session
from genut_service.status_main import create_status_app


@pytest.fixture
def status_client(db_engine: Engine) -> Iterator[TestClient]:
    """get_session을 테스트 DB로 오버라이드한 상태 서버 TestClient."""
    app = create_status_app()
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)

    def _override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client


def test_status_app_health_and_test_status_routes(status_client: TestClient) -> None:
    assert status_client.get("/health").json() == {"status": "ok"}
    # 프로덕트가 없으면 빈 요약 — 라우터가 붙어 있고 즉시 응답한다
    assert status_client.get("/api/test-status").json() == []


def test_status_app_excludes_management_apis(status_client: TestClient) -> None:
    """읽기 전용 서버 — job/프로덕트/GENUT 관리 API는 노출하지 않는다."""
    for path in ("/api/jobs", "/api/products", "/api/genuts", "/api/workers"):
        assert status_client.get(path).status_code == 404, path


def test_status_app_detail_unknown_name_404(status_client: TestClient) -> None:
    resp = status_client.get("/api/test-status/detail", params={"name": "nope"})
    assert resp.status_code == 404
