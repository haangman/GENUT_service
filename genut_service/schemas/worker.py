"""워커/큐 모니터링 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genut_service.schemas.common import UtcDatetime


class WorkerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    worker_status: str
    current_job_id: int | None
    enabled: bool


class QueueItem(BaseModel):
    job_id: int
    product_id: int
    submitted_at: UtcDatetime
    waiting_on_product: bool
