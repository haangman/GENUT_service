"""GENUT 인스턴스 CRUD."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance
from genut_service.schemas.genut import GenutCreate, GenutUpdate


def create_genut(session: Session, data: GenutCreate) -> GenutInstance:
    genut = GenutInstance(**data.model_dump())
    session.add(genut)
    session.commit()
    session.refresh(genut)
    return genut


def get_genut(session: Session, genut_id: int) -> GenutInstance | None:
    return session.get(GenutInstance, genut_id)


def list_genuts(session: Session, page: int, page_size: int) -> tuple[list[GenutInstance], int]:
    stmt = select(GenutInstance)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(
        session.scalars(
            stmt.order_by(GenutInstance.id).limit(page_size).offset((page - 1) * page_size)
        ).all()
    )
    return items, total


def update_genut(
    session: Session, genut_id: int, data: GenutUpdate
) -> GenutInstance | None:
    genut = session.get(GenutInstance, genut_id)
    if genut is None:
        return None
    payload = data.model_dump(exclude_unset=True)
    # credential key가 명시적 None이면 기존 값 유지
    if payload.get("ds_assist_credential_key") is None:
        payload.pop("ds_assist_credential_key", None)
    for key, value in payload.items():
        setattr(genut, key, value)
    session.commit()
    session.refresh(genut)
    return genut


def delete_genut(session: Session, genut_id: int) -> bool:
    genut = session.get(GenutInstance, genut_id)
    if genut is None:
        return False
    session.delete(genut)
    session.commit()
    return True
