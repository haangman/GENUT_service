"""M10: 프론트엔드 정적 서빙 + SPA fallback."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from genut_service.main import mount_frontend


def _make_dist(base: Path) -> Path:
    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)\n", encoding="utf-8")
    return dist


def test_spa_fallback_and_static_serving(tmp_path: Path) -> None:
    dist = _make_dist(tmp_path)
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    mount_frontend(app, dist)
    client = TestClient(app)

    assert client.get("/api/health").json() == {"status": "ok"}  # API 우선
    assert client.get("/assets/app.js").status_code == 200  # 정적 에셋
    assert "<html>app</html>" in client.get("/").text  # index
    assert "<html>app</html>" in client.get("/products").text  # SPA 라우트 폴백
    assert client.get("/api/unknown").status_code == 404  # 비-매칭 API는 폴백 안 함


def test_mount_frontend_noop_when_dist_missing(tmp_path: Path) -> None:
    app = FastAPI()
    mount_frontend(app, tmp_path / "missing")
    client = TestClient(app)
    assert client.get("/").status_code == 404


def test_mount_frontend_custom_index_for_status_app(tmp_path: Path) -> None:
    """멀티 엔트리 빌드: index_name="status.html"이면 status 엔트리로 폴백한다."""
    dist = _make_dist(tmp_path)
    (dist / "status.html").write_text("<html>status</html>", encoding="utf-8")
    app = FastAPI()
    mount_frontend(app, dist, index_name="status.html")
    client = TestClient(app)

    assert "<html>status</html>" in client.get("/").text
    assert "<html>status</html>" in client.get("/test-status").text  # SPA 폴백
    assert client.get("/assets/app.js").status_code == 200  # 에셋 공유
