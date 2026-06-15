"""공용 pytest 픽스처."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from genut_service.main import create_app


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient. 매 테스트마다 새 앱 인스턴스를 만든다."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
