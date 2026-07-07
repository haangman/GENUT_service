"""독립 테스트 현황 서버용 FastAPI 앱 팩토리.

메인 서비스(8000)와 별개 프로세스·별개 포트에서 "테스트 파일 현황"만 서빙한다.
- 라우터는 test-status(요약/상세/파일 뷰어)만 — job/제품 관리 API는 없다(읽기 전용).
- 스케줄러 없음: 스냅샷은 메인 프로세스의 리프레셔가 갱신하고, 이 서버는 같은
  DB(SQLite WAL)를 읽기만 한다. 메인이 죽어도 마지막 스냅샷을 계속 보여준다.
- 정적 서빙은 같은 frontend/dist를 쓰되 SPA fallback을 status.html로 한다.

메인 서버와 같은 작업 디렉터리(.env, DB 파일)에서 실행해야 한다:
`genut-service serve-status --port 8001`
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from genut_service.main import mount_frontend


def create_status_app() -> FastAPI:
    """테스트 현황 전용 FastAPI 애플리케이션을 생성한다."""
    app = FastAPI(title="GENUT_service test status", version="0.1.0")

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        """헬스 체크."""
        return {"status": "ok"}

    from genut_service.api.test_status import router as test_status_router

    app.include_router(test_status_router)

    mount_frontend(
        app,
        Path(__file__).resolve().parent.parent / "frontend" / "dist",
        index_name="status.html",
    )
    return app


app = create_status_app()
