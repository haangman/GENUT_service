"""테스트 생성 요청(Job) API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from genut_service.api.deps import PageParams, get_session
from genut_service.schemas.common import Page
from genut_service.schemas.job import JobCreate, JobEventRead, JobRead
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
    session: Session = Depends(get_session),
) -> Page[JobRead]:
    items, total = job_service.list_jobs(
        session, params.page, params.page_size, status_filter, product_id
    )
    return Page[JobRead](
        items=[JobRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: Session = Depends(get_session)) -> JobRead:
    job = job_service.get_job(session, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job을 찾을 수 없다")
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
