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
from genut_service.scheduler.engine import claim_jobs


def run_pending(session: Session, process: Callable = process_job) -> int:
    """한 번 claim하고 배정된 job들을 순서대로 처리한다. 처리한 수를 반환."""
    assignments = claim_jobs(session)
    for job_id, _ in assignments:
        process(session, job_id)
    return len(assignments)


class Scheduler:
    """운영용 백그라운드 스케줄러."""

    def __init__(self, session_factory, process: Callable = process_job, interval: float = 1.0):
        self._session_factory = session_factory
        self._process = process
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None

    def _run_one(self, job_id: int) -> None:
        with self._session_factory() as session:
            self._process(session, job_id)

    async def _loop(self) -> None:
        assert self._stop is not None
        running: set[asyncio.Task] = set()
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
            except Exception:  # noqa: BLE001 - 루프는 어떤 오류에도 죽지 않는다
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    async def start(self) -> None:
        # 시작 시 이전 실행에서 남은 stale 락을 정리한다
        try:
            from genut_service.scheduler.janitor import release_stale_locks

            with self._session_factory() as session:
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
