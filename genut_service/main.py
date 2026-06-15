"""FastAPI 앱 팩토리. lifespan에서 스케줄러를 기동할 예정(M5)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI


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

    return app


app = create_app()
