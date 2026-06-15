"""공용 pytest 픽스처."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

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
    app.state.run_scheduler = False  # 테스트에서는 백그라운드 스케줄러 비활성
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False, future=True)

    def _override_get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client


def _git_init_commit(path: Path) -> None:
    """주어진 디렉터리를 로컬 git repo로 초기화하고 전체를 커밋한다(기본 브랜치 main)."""
    for args in (
        ["init", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "tester"],
        ["add", "-A"],
        ["commit", "-m", "init"],
    ):
        subprocess.run(
            ["git", *args],
            cwd=path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )


@pytest.fixture(scope="session")
def fake_genut_repo(tmp_path_factory: pytest.TempPathFactory) -> dict:
    """fake GENUT CLI를 담은 로컬 git repo. runner가 clone하여 실행한다."""
    source = Path(__file__).parent / "fake_genut" / "fake_genut.py"
    repo = tmp_path_factory.mktemp("genut_repo")
    shutil.copy(source, repo / "fake_genut.py")
    _git_init_commit(repo)
    return {"repo_url": str(repo), "run_command": "python fake_genut.py"}


@pytest.fixture
def make_virtual_product(tmp_path_factory: pytest.TempPathFactory):
    """가상 프로덕트(로컬 git repo)를 만드는 팩토리.

    반환 dict은 Product 생성 필드 + git_url(로컬 경로) + patches를 포함한다.
    """

    def _make(
        name: str,
        mode: str = "cpp",
        sources: dict[str, str] | None = None,
        compdb_files: list[str] | None = None,
        scenario: dict | None = None,
        patches: list[dict] | None = None,
    ) -> dict:
        repo = tmp_path_factory.mktemp(f"prod_{name}")
        sources = sources or {"src/a.cpp": "// @genut-fn: foo\n"}
        for rel, content in sources.items():
            target = repo / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        (repo / "build").mkdir(parents=True, exist_ok=True)
        compdb_files = compdb_files if compdb_files is not None else list(sources.keys())
        compdb = [
            {
                "directory": str(repo / "build"),
                "command": "c++ -c",
                "file": str((repo / rel).resolve()),
            }
            for rel in compdb_files
        ]
        (repo / "build" / "compile_commands.json").write_text(
            json.dumps(compdb), encoding="utf-8"
        )
        if scenario is not None:
            (repo / "GENUT_SCENARIO.json").write_text(json.dumps(scenario), encoding="utf-8")

        _git_init_commit(repo)
        return {
            "name": name,
            "product_code": name,
            "git_url": str(repo),
            "git_ref": "main",
            "compile_db_rel": "build",
            "out_tests_rel": "tests/generated",
            "cmake_configure_cmd": "echo configure",
            "cmake_build_cmd": "echo build",
            "test_run_cmd": "echo test",
            "test_generation_mode": mode,
            "patches": patches or [],
            "repo": repo,
        }

    return _make
