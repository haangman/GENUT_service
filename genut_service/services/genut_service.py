"""GENUT 인스턴스 CRUD."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job
from genut_service.enums import INFLIGHT_STATUSES
from genut_service.schemas.genut import GenutCreate, GenutUpdate


class GenutInUseError(ValueError):
    """실행 중 job이 배정돼 있어 삭제할 수 없는 GENUT."""


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
    """GENUT 인스턴스를 삭제한다.

    jobs.genut_instance_id FK는 CASCADE가 아니므로, 종료된 job 이력은 남기되 배정
    표시만 지운다(이력의 종류 badge는 'GENUT'로 표시된다). 실행 중 job이 배정돼
    있으면 GenutInUseError.
    """
    genut = session.get(GenutInstance, genut_id)
    if genut is None:
        return False
    active = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.genut_instance_id == genut_id,
            Job.status.in_([s.value for s in INFLIGHT_STATUSES]),
        )
    )
    if active:
        raise GenutInUseError("실행 중인 job이 배정된 GENUT는 삭제할 수 없다")
    session.execute(
        update(Job)
        .where(Job.genut_instance_id == genut_id)
        .values(genut_instance_id=None)
    )
    session.delete(genut)
    session.commit()
    return True
