"""워커 본체: 배정된 job을 실행하고 종료 처리한다."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, JobEvent, Product
from genut_service.enums import JobPhase, JobStatus
from genut_service.runner import genut_runner, git_ops
from genut_service.scheduler.engine import finish_job


def _event(session: Session, job_id: int, level: str, phase: JobPhase, message: str) -> None:
    session.add(JobEvent(job_id=job_id, level=level, phase=phase.value, message=message))
    session.commit()


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
        )
    except git_ops.PatchError as exc:
        _event(session, job_id, "error", JobPhase.PATCH, f"patch 실패: {exc}")
        finish_job(session, job_id, JobStatus.FAILED, error=f"patch 실패: {exc}")
        return
    except git_ops.GitError as exc:
        _event(session, job_id, "error", JobPhase.CLONE, f"git 실패: {exc}")
        finish_job(session, job_id, JobStatus.FAILED, error=f"git 실패: {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - 어떤 예외든 job만 실패시키고 격리
        finish_job(session, job_id, JobStatus.FAILED, error=str(exc))
        return

    _event(session, job_id, "info", JobPhase.RUN, (result.stdout or "")[:2000])
    if result.success:
        finish_job(session, job_id, JobStatus.DONE, result_summary=result.result_summary or "ok")
    else:
        finish_job(
            session,
            job_id,
            JobStatus.FAILED,
            result_summary=result.result_summary,
            error=(result.stderr or "")[:2000] or "GENUT 실행 실패",
        )
