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


# 종료(terminal) 상태 집합 — 락 해제/폴링 중단 판정에 사용
TERMINAL_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELED}
)
