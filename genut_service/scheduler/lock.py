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


def release_lock(session: Session, product_id: int, job_id: int | None = None) -> None:
    """프로덕트 락을 해제한다(없으면 무시).

    job_id가 주어지면 **그 job이 소유한 락일 때만** 지운다 — 워치독에 회수된 job의
    워커 스레드가 뒤늦게 종료 처리를 호출해도, 그 사이 다른 job이 새로 획득한 락을
    지우지 못하게 한다("한 프로덕트 동시 1개" 불변식 보호).
    """
    lock = session.get(ProductLock, product_id)
    if lock is None:
        return
    if job_id is not None and lock.job_id != job_id:
        return
    session.delete(lock)
