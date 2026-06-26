"""프로덕트별 테스트 현황 API.

프로덕트의 compile_commands.json에서 테스트 대상 파일을 모으고, out_tests 폴더를
실시간 스캔해 대상 파일별 생성 테스트 파일을 매칭해 반환한다.

- 상세: GET /api/products/{id}/test-status (대상 파일별 테스트 파일)
- 요약: GET /api/test-status (전 프로덕트의 대상 파일 수·총 테스트 수)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.db.models import Product
from genut_service.schemas.test_status import ProductTestSummary, TargetFileStatus
from genut_service.services import product_service, test_status_service

router = APIRouter(prefix="/api/products", tags=["test-status"])
# 요약은 /api/products/{id} (int) 경로와 충돌하지 않도록 별도 prefix를 쓴다.
summary_router = APIRouter(prefix="/api/test-status", tags=["test-status"])


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


@summary_router.get("", response_model=list[ProductTestSummary])
def get_test_status_summary(
    session: Session = Depends(get_session),
) -> list[ProductTestSummary]:
    """전 프로덕트의 테스트 현황 요약. 각 프로덕트를 실시간 스캔한다.

    한 프로덕트 스캔이 실패해도(체크아웃 불가 등) 전체가 깨지지 않도록 그 항목은
    대상/테스트 수 0으로 처리한다.
    """
    products = session.scalars(select(Product).order_by(Product.id)).all()
    out: list[ProductTestSummary] = []
    for product in products:
        try:
            root = workspace.ensure_product_checkout(product)
            target_count, total_tests = test_status_service.summarize(root, product)
        except Exception:  # noqa: BLE001 - 한 프로덕트 실패가 요약 전체를 막지 않는다
            target_count, total_tests = 0, 0
        out.append(
            ProductTestSummary(
                product_id=product.id,
                name=product.name,
                product_code=product.product_code,
                test_generation_mode=product.test_generation_mode,
                code_path=product.code_path,
                target_file_count=target_count,
                total_test_count=total_tests,
            )
        )
    return out
