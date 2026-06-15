"""FastAPI 앱 팩토리. lifespan에서 스케줄러를 기동할 예정(M5)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """앱 수명주기. run_scheduler가 켜져 있으면 백그라운드 스케줄러를 돌린다."""
    scheduler = None
    if getattr(app.state, "run_scheduler", False):
        from genut_service.config import get_settings
        from genut_service.db.base import SessionLocal
        from genut_service.runner.worker import process_job
        from genut_service.scheduler.loop import Scheduler

        scheduler = Scheduler(SessionLocal, process_job, get_settings().scheduler_interval)
        await scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성한다."""
    from genut_service.config import get_settings

    app = FastAPI(title="GENUT_service", version="0.1.0", lifespan=lifespan)
    app.state.run_scheduler = get_settings().scheduler_autostart

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """헬스 체크."""
        return {"status": "ok"}

    from genut_service.api.files import router as files_router
    from genut_service.api.genuts import router as genuts_router
    from genut_service.api.jobs import router as jobs_router
    from genut_service.api.products import router as products_router
    from genut_service.api.workers import router as workers_router

    app.include_router(products_router)
    app.include_router(files_router)
    app.include_router(jobs_router)
    app.include_router(genuts_router)
    app.include_router(workers_router)

    # 빌드된 프론트엔드가 있으면 정적 서빙(SPA fallback). API 라우터 등록 이후에 한다.
    mount_frontend(app, Path(__file__).resolve().parent.parent / "frontend" / "dist")

    return app


def mount_frontend(app: FastAPI, dist_dir: Path) -> None:
    """frontend 빌드 산출물을 정적 서빙하고, 비-API 경로는 index.html로 폴백한다."""
    if not dist_dir.is_dir():
        return
    index_file = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):  # noqa: ANN202
        if full_path.startswith("api"):
            raise HTTPException(status_code=404)
        return FileResponse(str(index_file))


app = create_app()
