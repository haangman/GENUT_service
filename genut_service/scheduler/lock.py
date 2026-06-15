"""프로덕트 배타 락 헬퍼. product_locks.product_id PK가 원자적 배타를 보장한다."""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from genut_service.db.models import ProductLock


def try_acquire_lock(
    session: Session, product_id: int, job_id: int, genut_instance_id: int
) -> bool:
    """프로덕트 락을 시도한다. 이미 잠겨 있으면(PK 충돌) False."""
    session.add(
        ProductLock(product_id=product_id, job_id=job_id, genut_instance_id=genut_instance_id)
    )
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    return True


def release_lock(session: Session, product_id: int) -> None:
    """프로덕트 락을 해제한다(없으면 무시)."""
    lock = session.get(ProductLock, product_id)
    if lock is not None:
        session.delete(lock)
