"""워커 본체: 배정된 job을 실행하고 종료 처리한다."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Job, JobEvent, Product
from genut_service.enums import JobPhase, JobStatus
from genut_service.runner import genut_runner, git_ops, process_registry
from genut_service.scheduler.engine import finish_job


def _force_finish_failed(
    session: Session, job_id: int, error: str, status: JobStatus = JobStatus.FAILED
) -> None:
    """종료 처리(finish_job)가 예외로 실패했을 때의 최후 폴백.

    현재 세션을 롤백 후 finish_job을 재시도하고, 그래도 실패하면 새 세션으로 한 번 더
    시도한다. 취소된 job이면 status=CANCELED를 보존한다(기본 FAILED).
    """
    try:
        session.rollback()
        finish_job(session, job_id, status, error=error[:2000])
        return
    except Exception:  # noqa: BLE001 - 폴백이라 어떤 실패든 다음 수단으로 넘어간다
        pass
    try:
        from genut_service.db.base import SessionLocal

        with SessionLocal() as fresh:
            finish_job(fresh, job_id, status, error=error[:2000])
    except Exception:  # noqa: BLE001
        pass



def _cleanup_job_workspace(job_id: int) -> None:
    """job 워크스페이스(_workspaces/job_{id})에서 진행 로그(job.log)만 남기고 정리한다.

    job마다 만들어지는 프로덕트/GENUT clone·.venv·filelist는 정리하지 않으면
    (특히 auto 모드의 함수 단위 job으로) 무한 누적되어 디스크를 고갈시킨다.
    job.log는 로그 다운로드 API가 계속 사용하므로 보존한다. 정리 실패는 무시한다
    (파일 잠금 등 — job 결과에 영향을 주지 않는다).
    """
    root = Path(get_settings().workspace_root) / f"job_{job_id}"
    if not root.is_dir():
        return

    def _grant_write(func, path, _exc):  # noqa: ANN001 - Windows: git 객체 등 읽기 전용 해제
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    for entry in root.iterdir():
        try:
            if entry.name == "job.log":
                continue
            if entry.is_dir():
                shutil.rmtree(entry, onexc=_grant_write)
            else:
                entry.unlink(missing_ok=True)
        except OSError:
            pass


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
    log_path = workspace.job_log_path(job_id)

    # 실행 중 발생하는 단계/출력 이벤트를 즉시 기록한다.
    # (1) DB JobEvent → 모니터링 로그 실시간 갱신, (2) job.log 파일 append → 진행 중 다운로드.
    def emit(phase: str, level: str, message: str) -> None:
        text = message or ""
        session.add(JobEvent(job_id=job_id, level=level, phase=phase, message=text[:8000]))
        session.commit()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"[{phase}] {text}\n")
        except OSError:
            pass

    emit(JobPhase.SCHEDULE.value, "info", f"job 시작: product={product.name}, genut={genut.name}")

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

    # 실행 중 시작되는 서브프로세스를 강제 종료 레지스트리에 등록한다.
    def on_process(proc) -> None:  # noqa: ANN001
        process_registry.register(job_id, proc)

    # runner 실행. 취소 시 워커가 단계 경계에서 멈추도록 should_cancel 콜백을 전달한다.
    result = None
    run_error: Exception | None = None
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
            use_venv=settings.genut_use_venv,
            make_executor=make_executor,
            on_event=emit,
            on_process=on_process,
            should_cancel=lambda: process_registry.is_canceled(job_id),
        )
    except Exception as exc:  # noqa: BLE001 - 어떤 예외든 job만 격리해 종료시킨다
        run_error = exc

    # 종료 처리는 이 워커 스레드만 수행한다(단일 소유자 → 락/워커 경합 없음).
    # 취소 여부는 unregister 이전에 캡처한다(unregister가 취소 플래그를 지우므로).
    # 강제 종료로 서브프로세스가 죽어 예외가 났을 수 있어 취소를 가장 먼저 판정한다.
    canceled = process_registry.is_canceled(job_id)
    process_registry.unregister(job_id)
    try:
        if canceled:
            emit(JobPhase.COLLECT.value, "error", "강제 종료됨 (사용자 요청)")
            finish_job(session, job_id, JobStatus.CANCELED, error="사용자에 의해 강제 종료됨")
        elif run_error is not None:
            if isinstance(run_error, git_ops.PatchError):
                emit(JobPhase.PATCH.value, "error", f"patch 실패: {run_error}")
                finish_job(session, job_id, JobStatus.FAILED, error=f"patch 실패: {run_error}")
            elif isinstance(run_error, git_ops.GitError):
                emit(JobPhase.CLONE.value, "error", f"git 실패: {run_error}")
                finish_job(session, job_id, JobStatus.FAILED, error=f"git 실패: {run_error}")
            else:
                emit(JobPhase.RUN.value, "error", f"실행 오류: {run_error}")
                finish_job(session, job_id, JobStatus.FAILED, error=str(run_error))
        elif result.success:
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
    except Exception as finish_exc:  # noqa: BLE001 - 종료 처리 자체 실패 시 최후 폴백
        fallback = JobStatus.CANCELED if canceled else JobStatus.FAILED
        _force_finish_failed(session, job_id, f"종료 처리 실패: {finish_exc}", fallback)

    # 종료 후 워크스페이스 정리(로그만 보존) — 실패해도 job 결과에는 영향 없다
    try:
        _cleanup_job_workspace(job_id)
    except Exception:  # noqa: BLE001
        pass
