"""스케줄러 백그라운드 루프가 여러 워커로 동시에 실행하는지 검증."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from sqlalchemy import func, select

from genut_service.db.base import Base, make_engine, make_session_factory
from genut_service.db.models import GenutInstance, Job, Product
from genut_service.enums import JobStatus, WorkerStatus
from genut_service.scheduler.engine import finish_job
from genut_service.scheduler.loop import Scheduler


def _seed(session, n: int) -> None:
    for i in range(n):
        session.add(
            Product(
                name=f"P{i}", product_code=f"P{i}", git_url="u", compile_db_rel="build",
                out_tests_rel="tests", cmake_configure_cmd="c", cmake_build_cmd="b",
                test_run_cmd="r", test_generation_mode="cpp",
            )
        )
        session.add(
            GenutInstance(
                name=f"w{i}", repo_url="u", ds_assist_credential_key="k",
                ds_assist_send_system_name="s", worker_status=WorkerStatus.IDLE.value,
            )
        )
    session.flush()
    for pid in [p.id for p in session.scalars(select(Product))]:
        session.add(Job(product_id=pid))
    session.commit()


def test_scheduler_runs_jobs_concurrently(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{(tmp_path / 'loop.db').as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        _seed(session, 3)

    # 3개가 동시에 도달해야 통과하는 배리어 → 동시 실행 증명
    barrier = threading.Barrier(3, timeout=5)
    reached: list[int] = []

    def process(session, job_id):  # noqa: ANN001
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            finish_job(session, job_id, JobStatus.FAILED)
            return
        reached.append(job_id)
        finish_job(session, job_id, JobStatus.DONE)

    async def run() -> None:
        scheduler = Scheduler(session_factory, process, interval=0.05)
        await scheduler.start()
        for _ in range(120):
            with session_factory() as session:
                done = session.scalar(
                    select(func.count()).select_from(Job).where(Job.status == JobStatus.DONE.value)
                )
            if done == 3:
                break
            await asyncio.sleep(0.05)
        await scheduler.stop()

    asyncio.run(run())

    assert len(reached) == 3  # 3개 job이 동시에 배리어에 도달 = 동시 실행
    with session_factory() as session:
        done = session.scalar(
            select(func.count()).select_from(Job).where(Job.status == JobStatus.DONE.value)
        )
    assert done == 3
    engine.dispose()
