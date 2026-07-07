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
        status_refresh_interval: float | None = None,
    ):
        self._session_factory = session_factory
        self._process = process
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._refresh_task: asyncio.Task | None = None
        self._stop: asyncio.Event | None = None
        if status_refresh_interval is None:
            from genut_service.config import get_settings

            status_refresh_interval = get_settings().test_status_refresh_interval
        self._status_refresh_interval = status_refresh_interval
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

    # ── tick의 DB 작업들. 이벤트 루프가 아니라 to_thread에서 실행한다 ──
    # 워커 스레드들의 commit과 경합하면 SQLite busy 대기(최대 busy_timeout)로 각
    # statement가 블로킹될 수 있는데, 이벤트 루프에서 직접 돌리면 그 동안 모든 API
    # 응답이 함께 멈춘다. 호출은 순차 await이므로 단일 writer 전제는 유지된다.

    def _claim_tick(self) -> list[tuple[int, int]]:
        with self._session_factory() as session:
            return claim_jobs(session)

    def _auto_run_tick(self) -> list[int]:
        with self._session_factory() as session:
            auto_tick.enqueue_due_cycles(session)
            return auto_tick.claim_prep_jobs(session)

    def _sweep_tick(self) -> None:
        from genut_service.scheduler.janitor import reap_stuck_jobs, release_stale_locks

        with self._session_factory() as session:
            release_stale_locks(session)
            reap_stuck_jobs(session, self._stuck_timeout)

    def _purge_tick(self) -> None:
        from genut_service.config import get_settings
        from genut_service.scheduler.janitor import purge_old_job_events

        with self._session_factory() as session:
            purge_old_job_events(session, get_settings().job_event_retention_days)

    def _status_refresh_tick(self) -> None:
        from genut_service.services import test_status_snapshot_service

        with self._session_factory() as session:
            test_status_snapshot_service.refresh_snapshots(session)

    async def _status_refresh_loop(self) -> None:
        """테스트 현황 스냅샷 갱신 루프 — 메인 tick 루프와 분리해서 돈다.

        전체 프로덕트 스캔(clone 포함)은 수 분까지 걸릴 수 있어, 메인 루프에
        인라인하면 그 동안 claim이 멈춰 job 배정이 정지한다. 별도 태스크에서
        순차 실행(겹침 없음)하고 stop 이벤트를 공유한다.
        """
        assert self._stop is not None
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._status_refresh_tick)
            except Exception:  # noqa: BLE001 - 루프는 어떤 오류에도 죽지 않는다
                pass
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self._status_refresh_interval
                )
            except asyncio.TimeoutError:
                pass

    async def _loop(self) -> None:
        assert self._stop is not None

        running: set[asyncio.Task] = set()
        # 약 30초마다 안전망 sweep을 돈다(tick 간격 기준 환산).
        sweep_every = max(1, round(30.0 / max(self._interval, 0.1)))
        # 약 1시간마다 오래된 job 이벤트 로그를 정리한다(무한 증가 방지).
        purge_every = max(1, round(3600.0 / max(self._interval, 0.1)))
        tick = 0
        while not self._stop.is_set():
            try:
                # 매 tick마다 idle 워커만큼 배정하고, 완료를 기다리지 않고 즉시 디스패치한다.
                # (배치 전체 완료를 기다리지 않으므로 워커가 비는 즉시 다음 job을 잡아 롤링 병렬)
                assignments = await asyncio.to_thread(self._claim_tick)
                for job_id, _ in assignments:
                    task = asyncio.create_task(asyncio.to_thread(self._run_one, job_id))
                    running.add(task)
                    task.add_done_callback(running.discard)
                # auto 모드: 주기 도래 사이클 큐잉 + 준비(prep) job 디스패치.
                # 준비 job도 스레드에서 돌려 tick을 막지 않는다(git 갱신이 느릴 수 있음).
                prep_ids = await asyncio.to_thread(self._auto_run_tick)
                for job_id in prep_ids:
                    task = asyncio.create_task(asyncio.to_thread(self._run_prep, job_id))
                    running.add(task)
                    task.add_done_callback(running.discard)
                # 주기적 안전망: 누수된 락 해제 + 상한 초과로 고착된 job 회수(워커 사망 등).
                tick += 1
                if tick % sweep_every == 0:
                    await asyncio.to_thread(self._sweep_tick)
                if tick % purge_every == 0:
                    await asyncio.to_thread(self._purge_tick)
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
        if self._status_refresh_interval > 0:
            self._refresh_task = asyncio.create_task(self._status_refresh_loop())

    async def stop(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self._task is not None:
            await self._task
        if self._refresh_task is not None:
            await self._refresh_task
