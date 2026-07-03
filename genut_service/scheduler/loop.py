"""스케줄러 실행 루프.

- run_pending: claim → 배정된 각 job 처리(동기). E2E/테스트에서 결정론적으로 사용.
- Scheduler: 운영용 백그라운드 async 루프. 매 tick claim 후 배정된 job들을
  스레드 풀에서 병렬 처리한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlalchemy.orm import Session

from genut_service.runner.worker import process_job
from genut_service.scheduler import auto_tick
from genut_service.scheduler.engine import claim_jobs


def run_pending(session: Session, process: Callable = process_job) -> int:
    """한 번 claim하고 배정된 job들을 순서대로 처리한다. 처리한 수를 반환."""
    assignments = claim_jobs(session)
    for job_id, _ in assignments:
        process(session, job_id)
    return len(assignments)


class Scheduler:
    """운영용 백그라운드 스케줄러."""

    def __init__(
        self,
        session_factory,
        process: Callable = process_job,
        interval: float = 1.0,
        stuck_timeout: float | None = None,
    ):
        self._session_factory = session_factory
        self._process = process
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        if stuck_timeout is None:
            from genut_service.config import get_settings

            s = get_settings()
            # 정상 job의 최대 실행 시간보다 넉넉히 큰 상한 — 이를 넘기면 고착으로 보고 회수한다.
            # genut_run_timeout×3: venv 생성 + pip install + 본 실행이 각각 별도 타임아웃.
            # git_timeout×12: product/GENUT/ASSURE의 fetch·reset·clone·log + 패치 여유분.
            # (패치 수는 무제한이라 정적 상한이 완전하지 않다 — reap_stuck_jobs가 살아있는
            #  서브프로세스를 가진 job은 회수하지 않으므로 이 상한은 죽은 워커용 안전망이다.)
            stuck_timeout = s.genut_run_timeout * 3 + s.git_timeout * 12 + 600
        self._stuck_timeout = stuck_timeout

    def _run_one(self, job_id: int) -> None:
        with self._session_factory() as session:
            self._process(session, job_id)

    def _run_prep(self, job_id: int) -> None:
        with self._session_factory() as session:
            auto_tick.process_prep_job(session, job_id)

    async def _loop(self) -> None:
        assert self._stop is not None
        from genut_service.scheduler.janitor import reap_stuck_jobs, release_stale_locks

        running: set[asyncio.Task] = set()
        # 약 30초마다 안전망 sweep을 돈다(tick 간격 기준 환산).
        sweep_every = max(1, round(30.0 / max(self._interval, 0.1)))
        tick = 0
        while not self._stop.is_set():
            try:
                # 매 tick마다 idle 워커만큼 배정하고, 완료를 기다리지 않고 즉시 디스패치한다.
                # (배치 전체 완료를 기다리지 않으므로 워커가 비는 즉시 다음 job을 잡아 롤링 병렬)
                with self._session_factory() as session:
                    assignments = claim_jobs(session)
                for job_id, _ in assignments:
                    task = asyncio.create_task(asyncio.to_thread(self._run_one, job_id))
                    running.add(task)
                    task.add_done_callback(running.discard)
                # auto 모드: 주기 도래 사이클 큐잉 + 준비(prep) job 디스패치.
                # 준비 job도 스레드에서 돌려 tick을 막지 않는다(git 갱신이 느릴 수 있음).
                with self._session_factory() as session:
                    auto_tick.enqueue_due_cycles(session)
                    prep_ids = auto_tick.claim_prep_jobs(session)
                for job_id in prep_ids:
                    task = asyncio.create_task(asyncio.to_thread(self._run_prep, job_id))
                    running.add(task)
                    task.add_done_callback(running.discard)
                # 주기적 안전망: 누수된 락 해제 + 상한 초과로 고착된 job 회수(워커 사망 등).
                tick += 1
                if tick % sweep_every == 0:
                    with self._session_factory() as session:
                        release_stale_locks(session)
                        reap_stuck_jobs(session, self._stuck_timeout)
            except Exception:  # noqa: BLE001 - 루프는 어떤 오류에도 죽지 않는다
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def start(self) -> None:
        # 시작 시: 이전 실행에서 끊긴 job을 interrupted로 마킹하고, 남은 stale 락을 정리한다
        try:
            from genut_service.scheduler.janitor import (
                mark_interrupted_jobs,
                release_stale_locks,
            )

            with self._session_factory() as session:
                mark_interrupted_jobs(session)
                release_stale_locks(session)
        except Exception:  # noqa: BLE001
            pass
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            await self._task
