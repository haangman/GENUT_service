"""공용 pytest 픽스처."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import genut_service.db.models  # noqa: F401  (모델을 메타데이터에 등록)
from genut_service.db.base import Base
from genut_service.main import create_app


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient. 매 테스트마다 새 앱 인스턴스를 만든다."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db_session() -> Iterator[Session]:
    """격리된 인메모리 SQLite 세션. FK 강제(PRAGMA foreign_keys=ON) 활성."""
    engine: Engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with session_factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
