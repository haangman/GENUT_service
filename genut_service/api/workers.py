"""워커 상태 및 요청 큐 모니터링 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from genut_service.api.deps import get_session
from genut_service.schemas.worker import QueueItem, WorkerRead
from genut_service.services import monitoring_service

router = APIRouter(tags=["monitoring"])


@router.get("/api/workers", response_model=list[WorkerRead])
def list_workers(session: Session = Depends(get_session)) -> list[WorkerRead]:
    return [WorkerRead.model_validate(worker) for worker in monitoring_service.list_workers(session)]


@router.get("/api/queue", response_model=list[QueueItem])
def list_queue(session: Session = Depends(get_session)) -> list[QueueItem]:
    return [
        QueueItem(
            job_id=job.id,
            product_id=job.product_id,
            submitted_at=job.submitted_at,
            waiting_on_product=waiting,
        )
        for job, waiting in monitoring_service.list_queue(session)
    ]
