"""테스트 생성 요청(Job) API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import PageParams, get_session
from genut_service.enums import TERMINAL_STATUSES, JobStatus, Project
from genut_service.runner import process_registry
from genut_service.schemas.common import Page
from genut_service.schemas.job import AutoHistoryGroup, JobCreate, JobEventRead, JobRead
from genut_service.services import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def submit_job(data: JobCreate, session: Session = Depends(get_session)) -> JobRead:
    job = job_service.submit_request(session, data.product_id, data.files, data.function_name)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return JobRead.model_validate(job)


@router.get("", response_model=Page[JobRead])
def list_jobs(
    params: PageParams = Depends(),
    status_filter: str | None = Query(None, alias="status"),
    product_id: int | None = Query(None),
    origin: str | None = Query(None),
    kind: str | None = Query(None),
    project: Project | None = Query(None),
    session: Session = Depends(get_session),
) -> Page[JobRead]:
    items, total = job_service.list_jobs(
        session,
        params.page,
        params.page_size,
        status_filter,
        product_id,
        origin,
        kind,
        project=project.value if project else None,
    )
    return Page[JobRead](
        items=[JobRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


# 주의: `/{job_id}`보다 먼저 선언해야 한다(뒤에 두면 "auto-history"가 int 변환에 걸려 422).
@router.get("/auto-history", response_model=list[AutoHistoryGroup])
def auto_history(
    per_product: int = Query(3, ge=1, le=100),
    project: Project | None = Query(None),
    session: Session = Depends(get_session),
) -> list[AutoHistoryGroup]:
    """auto 프로덕트별 자동 실행 job 이력(프로덕트당 최근 per_product개 + 전체 수)."""
    groups = job_service.list_auto_history(
        session, per_product, project=project.value if project else None
    )
    return [
        AutoHistoryGroup(
            product_id=product.id,
            product_name=product.name,
            product_code=product.product_code,
            auto_interval_seconds=product.auto_interval_seconds,
            total=total,
            jobs=[JobRead.model_validate(job) for job in jobs],
        )
        for product, total, jobs in groups
    ]


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    job = job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    return JobRead.model_validate(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, session: Session = Depends(get_session)) -> None:
    """종결된 job을 이벤트·로그 파일과 함께 영구 삭제한다.

    실행 중/대기 중 job은 409 — 실행 중이면 먼저 강제 종료 후 삭제한다.
    """
    result = job_service.delete_job(session, job_id)
    if result == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    if result == "in_flight":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "완료된 job만 삭제할 수 있다 — 실행 중이면 먼저 강제 종료하세요",
        )


@router.post("/{job_id}/cancel", response_model=JobRead)
def cancel_job(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    """실행 중인 job을 강제 종료한다. 워커가 곧 상태를 canceled로 마무리한다."""
    job = job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    if job.status != JobStatus.RUNNING.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "실행 중인 job이 아니다")
    # 같은 프로세스의 워커가 돌리는 서브프로세스를 죽이고 취소 플래그를 세운다.
    # 종료(상태 전이·락 해제·워커 idle)는 API가 직접 하지 않고 그 job을 돌리는 워커
    # 스레드만 수행한다 — 살아있는 워커와 동시에 finish_job을 호출하면 락이 조기 해제돼
    # 같은 프로덕트에 다른 job이 재배정되는 경합이 생기기 때문이다.
    process_registry.cancel(job_id)
    return JobRead.model_validate(job)


@router.post("/{job_id}/rerun", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def rerun_job(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    """완료/실패/취소된 job과 동일한 입력으로 새 job을 큐에 추가한다."""
    original = job_service.get_job(session, job_id)
    if original is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    if original.status not in TERMINAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "완료된 job만 재수행할 수 있다")
    job = job_service.rerun_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return JobRead.model_validate(job)


@router.get("/{job_id}/logs", response_model=list[JobEventRead])
def get_job_logs(
    job_id: int,
    since: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[JobEventRead]:
    job = job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    events = job_service.list_events(session, job_id, since)
    return [JobEventRead.model_validate(event) for event in events]


@router.get("/{job_id}/log/download")
def download_job_log(job_id: int, session: Session = Depends(get_session)):
    """job 전체 진행 로그 파일을 다운로드한다. 실행 중에는 그 시점까지의 내용을 반환한다."""
    job = job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
    filename = f"job_{job_id}.log"
    path = workspace.job_log_path(job_id)
    if path.is_file():
        return FileResponse(str(path), media_type="text/plain", filename=filename)
    # 파일이 아직 없으면(시작 전/워크스페이스 정리됨) DB 이벤트로 구성
    events = job_service.list_events(session, job_id, 0)
    text = "\n".join(f"[{event.phase or '-'}] {event.message}" for event in events)
    return PlainTextResponse(
        text,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
