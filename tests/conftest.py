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
from genut_service.db.base import Base, get_session
from genut_service.main import create_app


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    """격리된 인메모리 SQLite 엔진. FK 강제(PRAGMA foreign_keys=ON) 활성."""
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
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """테스트 DB 세션 (db_engine 공유)."""
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)
    with session_factory() as session:
        yield session


@pytest.fixture
def client(db_engine: Engine) -> Iterator[TestClient]:
    """get_session을 테스트 DB로 오버라이드한 FastAPI TestClient."""
    app = create_app()
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)

    def _override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
