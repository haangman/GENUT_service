"""애플리케이션 설정 — .env에서 로드한다."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """서비스 전역 설정. 환경변수 또는 .env 파일로 주입한다."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 데이터베이스 (SQLite → 추후 Postgres)
    db_url: str = "sqlite:///./genut_service.db"

    # job별 작업 디렉터리 루트 (clone/patch/out 등이 생성됨)
    workspace_root: str = "./_workspaces"

    # GENUT CLI 실행 타임아웃(초) — GENUT 내부 루프가 길 수 있어 넉넉히 둔다
    genut_run_timeout: int = 1800

    # job 실행 시 GENUT 명령 전에 .venv 가상환경을 만들고 requirements.txt를 설치할지
    genut_use_venv: bool = True

    # git clone/fetch 등 분석성 명령 타임아웃(초)
    git_timeout: int = 300

    # 인프라성(클론 실패 등) 실패에 대한 서비스 레벨 재시도 횟수
    job_max_infra_retries: int = 1

    # 스케줄러 tick 간격(초)
    scheduler_interval: float = 1.0

    # 종료된 job의 이벤트 로그(JobEvent) 보존 기간(일). 0 이하 = 정리 안 함.
    # 이벤트는 GENUT 출력 한 줄당 1행이라 정리 없이는 무한 증가한다.
    # (전체 로그는 job.log 파일로 남으므로 다운로드는 계속 가능하다.)
    job_event_retention_days: int = 14

    # 테스트 현황 요약(GET /api/test-status) 캐시 TTL(초). 0 이하 = 캐시 안 함.
    # 요약은 전체 프로덕트의 체크아웃 파일시스템 풀스캔이라, 짧은 TTL로 반복 요청을
    # 흡수한다(그 사이 생성된 테스트는 최대 TTL만큼 늦게 보인다).
    test_status_cache_ttl: float = 30.0

    # FunctionExtractor(우분투 버전별 외부 바이너리) 배치 폴더.
    # 상대경로면 repo 루트 기준. 빈 문자열이면 비활성(항상 내장 파서 사용).
    func_extractor_dir: str = "tools/func_extractor"

    # FunctionExtractor 파일 1개 추출 타임아웃(초)
    func_extractor_timeout: int = 120

    # 앱 기동 시 백그라운드 스케줄러 루프를 자동 시작할지 (테스트에서는 끈다)
    scheduler_autostart: bool = True

    # Docker 실행 설정
    use_docker: bool = False  # True면 GENUT CLI를 컨테이너에서 실행
    docker_image: str = "genut-runner:latest"
    docker_cpus: float = 2.0
    docker_memory: str = "2g"


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴. 테스트에서는 캐시를 비우고 재생성할 수 있다."""
    return Settings()
