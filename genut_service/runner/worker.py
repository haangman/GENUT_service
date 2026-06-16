"""워커 본체: 배정된 job을 실행하고 종료 처리한다."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, JobEvent, Product
from genut_service.enums import JobPhase, JobStatus
from genut_service.runner import genut_runner, git_ops
from genut_service.scheduler.engine import finish_job


def process_job(
    session: Session,
    job_id: int,
    *,
    runner_run: Callable = genut_runner.run,
    debug: bool = True,
    enable_assure: bool = False,
) -> None:
    """배정된 job을 실행한다. 성공 시 DONE, 실패 시 FAILED로 종료(락 해제·워커 idle)."""
    job = session.get(Job, job_id)
    if job is None:
        return
    product = session.get(Product, job.product_id)
    genut = (
        session.get(GenutInstance, job.genut_instance_id)
        if job.genut_instance_id is not None
        else None
    )
    if product is None or genut is None:
        finish_job(session, job_id, JobStatus.FAILED, error="product 또는 GENUT 인스턴스 없음")
        return

    settings = get_settings()

    # 실행 중 발생하는 단계/출력 이벤트를 즉시 기록 → 모니터링 로그가 실시간 갱신
    def emit(phase: str, level: str, message: str) -> None:
        session.add(
            JobEvent(job_id=job_id, level=level, phase=phase, message=(message or "")[:4000])
        )
        session.commit()

    make_executor = None
    if settings.use_docker:
        from genut_service.docker.client import DockerExecutor

        def make_executor(job_root):  # noqa: ANN001
            return DockerExecutor(
                settings.docker_image,
                job_root,
                cpus=settings.docker_cpus,
                memory=settings.docker_memory,
            )

    try:
        result = runner_run(
            job,
            product,
            genut,
            workspace_root=settings.workspace_root,
            debug=debug,
            enable_assure=enable_assure,
            genut_timeout=settings.genut_run_timeout,
            git_timeout=settings.git_timeout,
            make_executor=make_executor,
            on_event=emit,
        )
    except git_ops.PatchError as exc:
        emit(JobPhase.PATCH.value, "error", f"patch 실패: {exc}")
        finish_job(session, job_id, JobStatus.FAILED, error=f"patch 실패: {exc}")
        return
    except git_ops.GitError as exc:
        emit(JobPhase.CLONE.value, "error", f"git 실패: {exc}")
        finish_job(session, job_id, JobStatus.FAILED, error=f"git 실패: {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - 어떤 예외든 job만 실패시키고 격리
        emit(JobPhase.RUN.value, "error", f"실행 오류: {exc}")
        finish_job(session, job_id, JobStatus.FAILED, error=str(exc))
        return

    if result.success:
        emit(JobPhase.COLLECT.value, "info", f"완료: {result.result_summary or 'ok'}")
        finish_job(session, job_id, JobStatus.DONE, result_summary=result.result_summary or "ok")
    else:
        detail = (result.stderr or result.stdout or "GENUT 실행 실패")[-2000:]
        emit(JobPhase.COLLECT.value, "error", f"실패: {detail[:500]}")
        finish_job(
            session,
            job_id,
            JobStatus.FAILED,
            result_summary=result.result_summary,
            error=detail or "GENUT 실행 실패",
        )
