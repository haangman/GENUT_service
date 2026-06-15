"""프로덕트 CRUD 비즈니스 로직 (FastAPI 비의존)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import Patch, Product
from genut_service.schemas.product import PatchIn, ProductCreate, ProductUpdate


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
    product = session.get(Product, product_id)
    if product is None:
        return False
    session.delete(product)
    session.commit()
    return True
