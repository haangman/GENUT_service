"""프로덕트 등록 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from genut_service.api.deps import PageParams, get_session
from genut_service.schemas.common import Page
from genut_service.schemas.product import ProductCreate, ProductRead, ProductUpdate
from genut_service.services import product_service

router = APIRouter(prefix="/api/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, session: Session = Depends(get_session)) -> ProductRead:
    try:
        product = product_service.create_product(session, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 프로덕트 이름이다")
    return ProductRead.model_validate(product)


@router.get("", response_model=Page[ProductRead])
def list_products(
    params: PageParams = Depends(),
    q: str | None = Query(None),
    session: Session = Depends(get_session),
) -> Page[ProductRead]:
    items, total = product_service.list_products(session, params.page, params.page_size, q)
    return Page[ProductRead](
        items=[ProductRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> ProductRead:
    product = product_service.get_product(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return ProductRead.model_validate(product)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, data: ProductUpdate, session: Session = Depends(get_session)
) -> ProductRead:
    try:
        product = product_service.update_product(session, product_id, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 프로덕트 이름이다")
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: Session = Depends(get_session)) -> None:
    if not product_service.delete_product(session, product_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
