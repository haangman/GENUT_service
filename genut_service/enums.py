"""도메인 열거형. DB에는 String으로 저장하고 여기서 값 검증을 한다."""

from __future__ import annotations

from enum import StrEnum


class TestGenerationMode(StrEnum):
    """GENUT가 생성하는 테스트 종류 (프로덕트 속성)."""

    C = "c"
    CPP = "cpp"
    KUNIT = "kunit"


class JobStatus(StrEnum):
    """Job 상태 머신."""

    QUEUED = "queued"
    ASSIGNED = "assigned"
    PREPARING = "preparing"
    RUNNING = "running"
    COLLECTING = "collecting"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"  # 서버 재시작 등으로 실행 도중 끊김


class JobKind(StrEnum):
    """job의 실행 경로 구분.

    GENUT만 워커(claim_jobs) 대상이고, 준비(prep) 종류는 스케줄러의 auto 단계가
    직접 실행한다(워커·product_locks 미사용).
    """

    GENUT = "genut"          # 실제 GENUT 실행
    AUTO_SCAN = "auto_scan"  # 누락 테스트 스캔(JJ작업) — 결과로 GENUT job을 큐잉
    AUTO_DIFF = "auto_diff"  # 코드 변경 함수 감지 — 결과로 GENUT job을 큐잉


class JobOrigin(StrEnum):
    """job 생성 주체 구분 (이력 페이지 필터 기준)."""

    MANUAL = "manual"  # 테스트 요청 페이지 등 수동 제출
    AUTO = "auto"      # auto 모드 주기 실행이 생성


# 준비(prep) job 종류 집합 — 스케줄러 auto 단계가 실행하는 kind
PREP_KINDS: frozenset[JobKind] = frozenset({JobKind.AUTO_SCAN, JobKind.AUTO_DIFF})


class LlmModel(StrEnum):
    """GENUT가 사용할 LLM 모델 (.env의 LLM_MODEL 값)."""

    GPT_OSS = "gptOss"
    SSCR_SE = "SSCR_SE"


class WorkerStatus(StrEnum):
    """GENUT 인스턴스(=워커) 상태."""

    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    DISABLED = "disabled"


class EventLevel(StrEnum):
    """job 이벤트 로그 레벨."""

    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class JobPhase(StrEnum):
    """runner 단계 구분 (이벤트 phase)."""

    SCHEDULE = "schedule"
    CLONE = "clone"
    PATCH = "patch"
    PREPARE = "prepare"
    RUN = "run"
    COLLECT = "collect"
    SCAN = "scan"  # auto_scan(누락 테스트 스캔) 준비 job
    DIFF = "diff"  # auto_diff(변경 함수 감지) 준비 job


# 종료(terminal) 상태 집합 — 락 해제/폴링 중단 판정에 사용
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED, JobStatus.INTERRUPTED}
)

# 실행 중(비-queued·비-terminal) 상태 집합 — 서버 재시작 시 '중단됨'으로 간주할 대상
INFLIGHT_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.ASSIGNED,
        JobStatus.PREPARING,
        JobStatus.RUNNING,
        JobStatus.COLLECTING,
        JobStatus.RETRYING,
    }
)
