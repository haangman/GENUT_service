"""Job 제출/조회 비즈니스 로직."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Job, JobEvent, Product
from genut_service.enums import JobStatus
from genut_service.services import compile_db_service


def submit_request(
    session: Session,
    product_id: int,
    files: list[str],
    function_name: str | None = None,
) -> Job | None:
    """compile-check를 수행해 included만 file_list로, 나머지는 excluded로 저장하고
    queued Job을 생성한다. 프로덕트가 없으면 None."""
    product = session.get(Product, product_id)
    if product is None:
        return None
    root = workspace.ensure_product_checkout(product)
    included, excluded = compile_db_service.split_inclusion(
        root, product.compile_db_rel, files
    )
    job = Job(
        product_id=product.id,
        function_name=function_name or None,
        file_list=included,
        excluded_files=excluded,
        status=JobStatus.QUEUED.value,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def list_jobs(
    session: Session,
    page: int,
    page_size: int,
    status: str | None = None,
    product_id: int | None = None,
) -> tuple[list[Job], int]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if product_id is not None:
        stmt = stmt.where(Job.product_id == product_id)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        session.scalars(
            stmt.order_by(Job.id.desc()).limit(page_size).offset((page - 1) * page_size)
        ).all()
    )
    return items, total


def list_events(session: Session, job_id: int, since: int = 0) -> list[JobEvent]:
    """job 이벤트(로그)를 id 오름차순으로 반환. since 이후(id > since)만."""
    stmt = (
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.id > since)
        .order_by(JobEvent.id)
    )
    return list(session.scalars(stmt).all())
