"""Job 제출/조회 비즈니스 로직."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Job, JobEvent, Product
from genut_service.enums import JobOrigin, JobStatus
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


def rerun_job(session: Session, job_id: int) -> Job | None:
    """원본 job과 동일한 입력으로 새 queued Job을 생성한다.

    product/file_list/excluded_files/function_name을 그대로 복사한다(compile-check 재실행
    없음 — "동일한 job"). genut_instance_id·timestamps·attempt 등은 복사하지 않아 스케줄러가
    새로 배정한다. 원본이 없거나 그 product가 삭제됐으면 None.
    """
    original = session.get(Job, job_id)
    if original is None:
        return None
    if session.get(Product, original.product_id) is None:
        return None
    job = Job(
        product_id=original.product_id,
        # kind/origin도 복사 — 준비(prep) job의 재수행은 새 queued 준비 job이 되어
        # 스케줄러 auto 단계가 다시 집어 실행한다.
        kind=original.kind,
        origin=original.origin,
        function_name=original.function_name,
        # JSON 컬럼 aliasing 방지를 위해 새 리스트로 복사한다.
        file_list=list(original.file_list or []),
        excluded_files=list(original.excluded_files or []),
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
    origin: str | None = None,
    kind: str | None = None,
    project: str | None = None,
) -> tuple[list[Job], int]:
    stmt = select(Job)
    if project:
        # 프로젝트 필터만 Product 조인이 필요하다(job은 product를 통해 프로젝트에 속한다)
        stmt = stmt.join(Product, Product.id == Job.product_id).where(
            Product.project == project
        )
    if status:
        stmt = stmt.where(Job.status == status)
    if product_id is not None:
        stmt = stmt.where(Job.product_id == product_id)
    if origin:
        stmt = stmt.where(Job.origin == origin)
    if kind:
        stmt = stmt.where(Job.kind == kind)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        session.scalars(
            stmt.order_by(Job.id.desc()).limit(page_size).offset((page - 1) * page_size)
        ).all()
    )
    return items, total


def list_auto_history(
    session: Session, per_product: int = 3, project: str | None = None
) -> list[tuple[Product, int, list[Job]]]:
    """auto 프로덕트별 origin='auto' job 이력을 (프로덕트, 전체 수, 최근 N개)로 반환한다.

    window function(row_number/count OVER PARTITION BY) 1쿼리로 프로덕트별 최근
    per_product개를 뽑는다(SQLite 3.25+/Postgres 공통). auto job이 없는 auto
    프로덕트도 빈 그룹으로 포함하고, **auto_run을 해제한 프로덕트라도 auto job
    이력이 있으면 포함**한다 — 그렇지 않으면 남은 job(실행 중 포함)의 로그 열람·
    강제 종료 경로가 UI에서 사라진다. 정렬: 프로덕트 id 오름차순, job id 내림차순.
    """
    products_stmt = select(Product).where(
        or_(
            Product.auto_run.is_(True),
            Product.id.in_(
                select(Job.product_id).where(Job.origin == JobOrigin.AUTO.value)
            ),
        )
    )
    if project:
        products_stmt = products_stmt.where(Product.project == project)
    products = list(session.scalars(products_stmt.order_by(Product.id)))
    if not products:
        return []

    rn = (
        func.row_number()
        .over(partition_by=Job.product_id, order_by=Job.id.desc())
        .label("rn")
    )
    per_total = func.count().over(partition_by=Job.product_id).label("total")
    ranked = (
        select(Job.id.label("job_id"), rn, per_total)
        .where(Job.origin == JobOrigin.AUTO.value)
        .subquery()
    )
    rows = session.execute(
        select(Job, ranked.c.total)
        .join(ranked, ranked.c.job_id == Job.id)
        .where(ranked.c.rn <= per_product)
        .order_by(Job.product_id.asc(), Job.id.desc())
    ).all()

    jobs_by_product: dict[int, list[Job]] = {}
    totals: dict[int, int] = {}
    for job, total in rows:
        jobs_by_product.setdefault(job.product_id, []).append(job)
        totals[job.product_id] = total

    return [
        (product, totals.get(product.id, 0), jobs_by_product.get(product.id, []))
        for product in products
    ]


def list_events(session: Session, job_id: int, since: int = 0) -> list[JobEvent]:
    """job 이벤트(로그)를 id 오름차순으로 반환. since 이후(id > since)만."""
    stmt = (
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.id > since)
        .order_by(JobEvent.id)
    )
    return list(session.scalars(stmt).all())
