"""프로덕트별 테스트 현황 API.

프로덕트의 compile_commands.json에서 테스트 대상 파일을 모으고, out_tests 폴더를
실시간 스캔해 대상 파일별 생성 테스트 파일을 매칭해 반환한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.schemas.test_status import TargetFileStatus
from genut_service.services import product_service, test_status_service

router = APIRouter(prefix="/api/products", tags=["test-status"])


@router.get("/{product_id}/test-status", response_model=list[TargetFileStatus])
def get_test_status(
    product_id: int,
    session: Session = Depends(get_session),
) -> list[TargetFileStatus]:
    product = product_service.get_product(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    root = workspace.ensure_product_checkout(product)
    rows = test_status_service.build_status(root, product)
    return [TargetFileStatus.model_validate(row) for row in rows]
