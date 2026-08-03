"""Job 제출/조회 비즈니스 로직."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Job, JobEvent, Product
from genut_service.enums import (
    INFLIGHT_STATUSES,
    TERMINAL_STATUSES,
    JobOrigin,
    JobStatus,
)
from genut_service.fs import rmtree_force
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


def cancel_all_jobs(session: Session, product_id: int) -> tuple[int, int]:
    """프로덕트의 미종결 job을 일괄 중지한다. 반환: (즉시 취소된 대기 수, 중지 요청된 실행 수).

    대기(queued) job은 워커/락 소유자가 없으므로 **조건부 일괄 UPDATE**로 즉시
    canceled 확정한다 — `status='queued'` 조건이라 스케줄러 claim과 경합해도 이중
    처리가 없다(그 사이 running으로 넘어간 job은 아래 실행 중 처리로 잡힌다).
    실행 중 job은 단건 강제 종료와 동일하게 process_registry에 취소를 걸기만 하고,
    종료 확정(상태 전이·락 해제)은 그 job을 돌리는 워커가 수행한다(단일 소유자).
    GENUT job과 준비 job(auto_diff/auto_scan) 모두 대상이다.
    """
    from genut_service.runner import process_registry

    result = session.execute(
        update(Job)
        .where(Job.product_id == product_id, Job.status == JobStatus.QUEUED.value)
        .values(
            status=JobStatus.CANCELED.value,
            finished_at=datetime.now(timezone.utc),
            error="사용자에 의해 일괄 취소됨",
        )
    )
    session.commit()
    running_ids = list(
        session.scalars(
            select(Job.id).where(
                Job.product_id == product_id, Job.status == JobStatus.RUNNING.value
            )
        )
    )
    for job_id in running_ids:
        process_registry.cancel(job_id)
    return result.rowcount or 0, len(running_ids)


def delete_finished_jobs(session: Session, product_id: int) -> int:
    """프로덕트의 종결(terminal) job을 이벤트·로그 폴더와 함께 전부 삭제한다. 삭제 수 반환."""
    terminal = [status.value for status in TERMINAL_STATUSES]
    jobs = list(
        session.scalars(
            select(Job).where(Job.product_id == product_id, Job.status.in_(terminal))
        )
    )
    job_ids = [job.id for job in jobs]
    for job in jobs:
        session.delete(job)  # job_events는 cascade
    session.commit()
    for job_id in job_ids:
        rmtree_force(workspace.job_log_path(job_id).parent)
    return len(job_ids)


def delete_job(session: Session, job_id: int) -> str:
    """종결(terminal) job을 이벤트·워크스페이스 로그와 함께 영구 삭제한다.

    반환: "deleted" | "not_found" | "in_flight". 실행 중/대기 중 job은 워커·스케줄러가
    소유하므로 삭제하지 않는다(호출부가 409로 매핑 — 강제 종료 후 삭제하는 흐름).
    """
    job = session.get(Job, job_id)
    if job is None:
        return "not_found"
    if job.status not in TERMINAL_STATUSES:
        return "in_flight"
    session.delete(job)  # job_events는 cascade로 함께 삭제된다
    session.commit()
    # 워크스페이스 잔여 폴더(job.log, 임시 clone 잔재 등) 정리 — 실패해도 삭제 자체는 유효
    rmtree_force(workspace.job_log_path(job_id).parent)
    return "deleted"


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


class AutoHistoryRow(NamedTuple):
    """auto 이력 그룹 1건.

    running/queued는 그룹 헤더의 상태 배지(running·대기·idle) 근거다. 최근 N개
    (jobs)만으로는 판정할 수 없다 — 대기 job이 많으면 실행 중 job이 최근 N개
    밖으로 밀리기 때문에 전체를 대상으로 따로 센다.
    """

    product: Product
    total: int
    jobs: list[Job]
    running: int
    queued: int


def list_auto_history(
    session: Session, per_product: int = 3, project: str | None = None
) -> list[AutoHistoryRow]:
    """auto 프로덕트별 origin='auto' job 이력을 그룹(AutoHistoryRow)으로 반환한다.

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

    running, queued = _count_active_auto_jobs(session)

    return [
        AutoHistoryRow(
            product=product,
            total=totals.get(product.id, 0),
            jobs=jobs_by_product.get(product.id, []),
            running=running.get(product.id, 0),
            queued=queued.get(product.id, 0),
        )
        for product in products
    ]


def _count_active_auto_jobs(session: Session) -> tuple[dict[int, int], dict[int, int]]:
    """프로덕트별 (실행 중, 대기 중) auto job 수를 센다.

    실행 중은 in-flight 상태 전체(현재 실제 전이는 running뿐이지만 assigned 등이
    쓰이게 돼도 idle로 오표시되지 않게 한다), 대기 중은 queued다. 준비 job
    (auto_scan/auto_diff)도 프로덕트를 점유하므로 kind 구분 없이 함께 센다.
    """
    active = (*(status.value for status in INFLIGHT_STATUSES), JobStatus.QUEUED.value)
    rows = session.execute(
        select(Job.product_id, Job.status, func.count())
        .where(Job.origin == JobOrigin.AUTO.value, Job.status.in_(active))
        .group_by(Job.product_id, Job.status)
    ).all()

    running: dict[int, int] = {}
    queued: dict[int, int] = {}
    for product_id, status, count in rows:
        target = queued if status == JobStatus.QUEUED.value else running
        target[product_id] = target.get(product_id, 0) + count
    return running, queued


def list_events(session: Session, job_id: int, since: int = 0) -> list[JobEvent]:
    """job 이벤트(로그)를 id 오름차순으로 반환. since 이후(id > since)만."""
    stmt = (
        select(JobEvent)
        .where(JobEvent.job_id == job_id, JobEvent.id > since)
        .order_by(JobEvent.id)
    )
    return list(session.scalars(stmt).all())
