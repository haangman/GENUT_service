"""프로덕트 CRUD 비즈니스 로직 (FastAPI 비의존)."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from genut_service.db.models import Job, Patch, Product
from genut_service.enums import INFLIGHT_STATUSES, JobStatus
from genut_service.schemas.product import PatchIn, ProductCreate, ProductUpdate


class ProductInUseError(ValueError):
    """대기/실행 중 job이 있어 삭제할 수 없는 프로덕트."""


def _set_patches(product: Product, patches: list[PatchIn]) -> None:
    product.patches.clear()
    for patch in patches:
        product.patches.append(
            Patch(order_index=patch.order_index, name=patch.name, content=patch.content)
        )


def create_product(session: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump(exclude={"patches"}))
    _set_patches(product, data.patches)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def get_product(session: Session, product_id: int) -> Product | None:
    return session.get(Product, product_id)


def list_products(
    session: Session, page: int, page_size: int, q: str | None = None
) -> tuple[list[Product], int]:
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        session.scalars(
            stmt.order_by(Product.id).limit(page_size).offset((page - 1) * page_size)
        ).all()
    )
    return items, total


def update_product(
    session: Session, product_id: int, data: ProductUpdate
) -> Product | None:
    product = session.get(Product, product_id)
    if product is None:
        return None
    payload = data.model_dump(exclude_unset=True, exclude={"patches"})
    for key, value in payload.items():
        setattr(product, key, value)
    if data.patches is not None:
        _set_patches(product, data.patches)
    session.commit()
    session.refresh(product)
    return product


def delete_product(session: Session, product_id: int) -> bool:
    """프로덕트와 그 job 이력을 삭제한다.

    jobs.product_id FK는 CASCADE가 아니므로(이력 보존이 기본), 삭제 전에 이 프로덕트의
    job을 함께 지워야 한다. 대기/실행 중 job이 있으면 ProductInUseError — 실행 중
    삭제로 워커·락이 꼬이는 것을 막는다. 이벤트/패치/락은 DB FK CASCADE로 정리된다.
    """
    product = session.get(Product, product_id)
    if product is None:
        return False
    active_statuses = [s.value for s in INFLIGHT_STATUSES] + [JobStatus.QUEUED.value]
    active = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(Job.product_id == product_id, Job.status.in_(active_statuses))
    )
    if active:
        raise ProductInUseError("실행 중이거나 대기 중인 job이 있는 프로덕트는 삭제할 수 없다")
    # ORM cascade 간섭 없이 core delete로 처리(job_events는 FK CASCADE로 함께 삭제)
    session.execute(delete(Job).where(Job.product_id == product_id))
    session.execute(delete(Product).where(Product.id == product_id))
    session.commit()
    return True
