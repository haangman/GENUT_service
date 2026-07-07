"""테스트 현황 API (동명 프로덕트를 이름 1개로 합산).

프로덕트의 compile_commands.json에서 테스트 대상 파일을 모으고, out_tests 폴더를
실시간 스캔해 대상 파일별 생성 테스트 파일을 매칭한다. 같은 이름의 프로덕트(변이)는
경로 기준 합집합으로 합산한다.

- 요약: GET /api/test-status            (이름별 대상 파일 수·총 테스트 수)
- 상세: GET /api/test-status/detail?name=<name>  (이름의 대상 파일·테스트 파일, 출처 포함)
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.config import get_settings
from genut_service.db.models import Product
from genut_service.paths import PathValidationError, normalize_rel_path
from genut_service.schemas.test_status import (
    FileContent,
    NameTestSummary,
    TargetFileStatus,
)
from genut_service.services import test_status_service

router = APIRouter(prefix="/api/test-status", tags=["test-status"])

# 요약 캐시. 요약은 등록 프로덕트 전체의 체크아웃 파일시스템 풀스캔이라 요청 1건이
# 무겁다 — 짧은 TTL로 폴링/중복 요청을 흡수한다. 프로덕트 목록이 바뀌면(등록/수정)
# 지문(fingerprint)이 달라져 즉시 무효화되고, 파일시스템 변화만은 최대 TTL만큼 늦게 보인다.
_summary_cache: dict = {"key": None, "expires": 0.0, "value": None}


def clear_summary_cache() -> None:
    """요약 캐시 초기화(테스트/수동 무효화용)."""
    _summary_cache.update(key=None, expires=0.0, value=None)


def _scan_pairs(products: list[Product]) -> list[tuple[str, list[dict]]]:
    """동기 스캔 폴백(스냅샷 부재 시). 구현은 services.test_status_service.scan_group."""
    return test_status_service.scan_group(products)


@router.get("", response_model=list[NameTestSummary])
def get_test_status_summary(
    session: Session = Depends(get_session),
) -> list[NameTestSummary]:
    """이름으로 묶은 테스트 현황 요약. 같은 이름의 변이는 합집합으로 합산한다."""
    products = session.scalars(select(Product).order_by(Product.id)).all()

    ttl = get_settings().test_status_cache_ttl
    cache_key = tuple((p.id, str(p.updated_at)) for p in products)
    now = time.monotonic()
    if ttl > 0 and _summary_cache["key"] == cache_key and now < _summary_cache["expires"]:
        return _summary_cache["value"]

    # 이름별 그룹(등록 순서 보존)
    groups: dict[str, list[Product]] = {}
    for product in products:
        groups.setdefault(product.name, []).append(product)

    out: list[NameTestSummary] = []
    for name in sorted(groups):
        group = groups[name]
        merged = test_status_service.merge_status(_scan_pairs(group))
        out.append(
            NameTestSummary(
                name=name,
                product_codes=[p.product_code for p in group],
                test_generation_mode=group[0].test_generation_mode,
                target_file_count=len(merged),
                total_test_count=sum(row["test_count"] for row in merged),
                total_case_count=sum(row["case_count"] for row in merged),
                total_fail_count=sum(row["fail_count"] for row in merged),
            )
        )
    if ttl > 0:
        _summary_cache.update(key=cache_key, expires=now + ttl, value=out)
    return out


@router.get("/detail", response_model=list[TargetFileStatus])
def get_test_status_detail(
    name: str = Query(...),
    session: Session = Depends(get_session),
) -> list[TargetFileStatus]:
    """이름의 모든 변이를 합산한 대상 파일·테스트 파일 상세(파일별 출처 product_codes 포함)."""
    group = list(session.scalars(select(Product).where(Product.name == name)))
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    merged = test_status_service.merge_status(_scan_pairs(group))
    return [TargetFileStatus.model_validate(row) for row in merged]


def _within(target: Path, base: Path) -> bool:
    """target(resolve됨)이 base(resolve됨) 하위인지."""
    return target == base or target.is_relative_to(base)


@router.get("/file", response_model=FileContent)
def get_test_file(
    code: str = Query(...),
    path: str = Query(...),
    session: Session = Depends(get_session),
) -> FileContent:
    """테스트 코드/로그 파일 1건의 내용을 반환한다(뷰어용).

    허용 루트는 프로덕트의 out_tests 폴더와 그 형제 `_Fail`/`_debug_log`뿐이다.
    경로는 `..`를 거부(400)하고, 허용 루트 밖이거나 없는 파일은 404다.
    """
    product = session.scalars(
        select(Product).where(Product.product_code == code)
    ).first()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    try:
        rel = normalize_rel_path(path)
    except PathValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "허용되지 않는 경로다") from exc

    root = workspace.ensure_product_checkout(product)
    target = (root / rel).resolve()
    allowed = test_status_service.allowed_roots(root, product)
    if not any(_within(target, base) for base in allowed) or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없다")
    return FileContent(path=rel, content=target.read_text(encoding="utf-8", errors="replace"))
