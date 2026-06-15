"""GENUT 인스턴스 등록 API. credential key는 응답에 포함하지 않는다."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from genut_service.api.deps import PageParams, get_session
from genut_service.schemas.common import Page
from genut_service.schemas.genut import GenutCreate, GenutRead, GenutUpdate
from genut_service.services import genut_service

router = APIRouter(prefix="/api/genuts", tags=["genuts"])


@router.post("", response_model=GenutRead, status_code=status.HTTP_201_CREATED)
def create_genut(data: GenutCreate, session: Session = Depends(get_session)) -> GenutRead:
    try:
        genut = genut_service.create_genut(session, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 GENUT 이름이다")
    return GenutRead.model_validate(genut)


@router.get("", response_model=Page[GenutRead])
def list_genuts(
    params: PageParams = Depends(), session: Session = Depends(get_session)
) -> Page[GenutRead]:
    items, total = genut_service.list_genuts(session, params.page, params.page_size)
    return Page[GenutRead](
        items=[GenutRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{genut_id}", response_model=GenutRead)
def get_genut(genut_id: int, session: Session = Depends(get_session)) -> GenutRead:
    genut = genut_service.get_genut(session, genut_id)
    if genut is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GENUT를 찾을 수 없다")
    return GenutRead.model_validate(genut)


@router.put("/{genut_id}", response_model=GenutRead)
def update_genut(
    genut_id: int, data: GenutUpdate, session: Session = Depends(get_session)
) -> GenutRead:
    try:
        genut = genut_service.update_genut(session, genut_id, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 GENUT 이름이다")
    if genut is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GENUT를 찾을 수 없다")
    return GenutRead.model_validate(genut)


@router.delete("/{genut_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_genut(genut_id: int, session: Session = Depends(get_session)) -> None:
    if not genut_service.delete_genut(session, genut_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GENUT를 찾을 수 없다")
