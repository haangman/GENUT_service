"""FastAPI 앱 팩토리. lifespan에서 스케줄러를 기동할 예정(M5)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    """앱 수명주기. M5에서 여기서 스케줄러 루프를 시작/정지한다."""
    # startup
    yield
    # shutdown


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 생성한다."""
    app = FastAPI(title="GENUT_service", version="0.1.0", lifespan=lifespan)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """헬스 체크."""
        return {"status": "ok"}

    from genut_service.api.products import router as products_router

    app.include_router(products_router)

    return app


app = create_app()
