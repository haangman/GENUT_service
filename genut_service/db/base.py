"""SQLAlchemy 엔진/세션 팩토리 및 선언적 Base.

SQLite에서는 WAL + busy_timeout + foreign_keys 프라그마를 적용해
단일 writer(스케줄러) 설계와 잘 맞도록 한다. Postgres로 이식 시
DB_URL만 바꾸면 되도록 SQLite 전용 기능에 의존하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from genut_service.config import get_settings


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스."""


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """SQLite 연결마다 WAL/busy_timeout/foreign_keys를 켠다."""

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def make_engine(db_url: str | None = None) -> Engine:
    """주어진(또는 설정의) DB_URL로 엔진을 만든다."""
    url = db_url or get_settings().db_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        _apply_sqlite_pragmas(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """엔진에 바인딩된 세션 팩토리를 만든다."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
        future=True,
    )


# 애플리케이션 전역 엔진/세션 (테스트는 자체 엔진을 만들어 의존성 오버라이드)
engine: Engine = make_engine()
SessionLocal: sessionmaker[Session] = make_session_factory(engine)


def get_session() -> Iterator[Session]:
    """FastAPI 의존성: 요청 스코프 세션을 제공한다."""
    with SessionLocal() as session:
        yield session
