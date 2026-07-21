"""테스트 현황 API (같은 프로젝트의 동명 프로덕트를 이름 1개로 합산).

프로덕트의 compile_commands.json에서 테스트 대상 파일을 모으고, out_tests 폴더를
실시간 스캔해 대상 파일별 생성 테스트 파일을 매칭한다. 같은 (프로젝트, 이름)의
프로덕트(변이)는 경로 기준 합집합으로 합산한다.

- 요약: GET /api/test-status?project=<p>  (프로젝트의 이름별 대상 파일 수·총 테스트 수)
- 상세: GET /api/test-status/detail?project=<p>&name=<name>
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.config import get_settings
from genut_service.db.models import Product, TestStatusSnapshot
from genut_service.enums import Project
from genut_service.paths import PathValidationError, normalize_rel_path
from genut_service.schemas.test_status import (
    FileContent,
    NameTestSummary,
    TargetFileStatus,
)
from genut_service.services import test_status_service, test_status_snapshot_service
from genut_service.services.code_pull_service import (
    CodePathBusyError,
    raise_if_code_path_busy,
)

router = APIRouter(prefix="/api/test-status", tags=["test-status"])

# 요약 캐시(프로젝트별 엔트리). 요약은 프로젝트 내 프로덕트 전체의 체크아웃 파일시스템
# 풀스캔이라 요청 1건이 무겁다 — 짧은 TTL로 폴링/중복 요청을 흡수한다. 프로덕트 목록이
# 바뀌면(등록/수정) 지문(fingerprint)이 달라져 즉시 무효화되고, 파일시스템 변화만은
# 최대 TTL만큼 늦게 보인다. 프로젝트별로 나눠 서로 캐시를 밀어내지 않게 한다.
_summary_cache: dict[str, dict] = {}


def clear_summary_cache() -> None:
    """요약 캐시 초기화(테스트/수동 무효화용)."""
    _summary_cache.clear()


def _scan_pairs(products: list[Product]) -> list[tuple[str, list[dict]]]:
    """동기 스캔 폴백(스냅샷 부재 시). 구현은 services.test_status_service.scan_group."""
    return test_status_service.scan_group(products)


@router.get("", response_model=list[NameTestSummary])
def get_test_status_summary(
    project: Project = Query(Project.ULYSSES),
    session: Session = Depends(get_session),
) -> list[NameTestSummary]:
    """프로젝트의 이름별 테스트 현황 요약. 같은 이름의 변이는 합집합으로 합산한다.

    스냅샷(백그라운드 리프레셔가 미리 계산)이 있으면 즉시 반환하고, 없는 이름만
    실시간 스캔으로 폴백한다(스케줄러가 꺼진 개발/테스트 환경 포함).
    """
    products = session.scalars(
        select(Product).where(Product.project == project.value).order_by(Product.id)
    ).all()

    ttl = get_settings().test_status_cache_ttl
    cache_key = tuple((p.id, str(p.updated_at)) for p in products)
    now = time.monotonic()
    cached = _summary_cache.get(project.value)
    if ttl > 0 and cached is not None and cached["key"] == cache_key and now < cached["expires"]:
        return cached["value"]

    # 이름별 그룹(등록 순서 보존)
    groups: dict[str, list[Product]] = {}
    for product in products:
        groups.setdefault(product.name, []).append(product)

    snapshots = test_status_snapshot_service.load_summaries(session, project.value)

    out: list[NameTestSummary] = []
    for name in sorted(groups):
        group = groups[name]
        snapshot = snapshots.get(name)
        if snapshot is not None:
            summary, generated_at = snapshot
            out.append(NameTestSummary(**summary, generated_at=generated_at))
            continue
        merged = test_status_service.merge_status(_scan_pairs(group))
        out.append(
            NameTestSummary(
                project=project.value,
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
        _summary_cache[project.value] = {"key": cache_key, "expires": now + ttl, "value": out}
    return out


@router.get("/detail", response_model=list[TargetFileStatus])
def get_test_status_detail(
    name: str = Query(...),
    project: Project = Query(Project.ULYSSES),
    session: Session = Depends(get_session),
) -> list[TargetFileStatus]:
    """(프로젝트, 이름)의 모든 변이를 합산한 대상 파일·테스트 파일 상세
    (파일별 출처 product_codes 포함).

    스냅샷이 있으면 즉시 반환하고, 없으면 실시간 스캔으로 폴백한다.
    """
    group = list(
        session.scalars(
            select(Product).where(
                Product.project == project.value, Product.name == name
            )
        )
    )
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    detail = test_status_snapshot_service.load_detail(session, project.value, name)
    if detail is None:
        detail = test_status_service.merge_status(_scan_pairs(group))
    return [TargetFileStatus.model_validate(row) for row in detail]


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
    체크아웃이 없어도 clone하지 않는다(독립 상태 서버에서 부작용/블로킹 방지) — 404.
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

    root = workspace.existing_product_checkout(product)
    if root is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없다")
    target = (root / rel).resolve()
    allowed = test_status_service.allowed_roots(root, product)
    if not any(_within(target, base) for base in allowed) or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없다")
    return FileContent(path=rel, content=target.read_text(encoding="utf-8", errors="replace"))


# ---- 삭제(mutation) API — 메인 앱 전용 라우터 -------------------------------------
# 읽기 전용 독립 현황 서버(serve-status)는 위 `router`만 마운트하므로, 삭제는 이
# 별도 라우터에 두어 메인 앱(main.py)에서만 노출한다.
mutation_router = APIRouter(prefix="/api/test-status", tags=["test-status"])


def _invalidate_after_delete(session: Session, project: str, name: str) -> None:
    """삭제 직후 요약 캐시와 (project, name) 스냅샷을 무효화한다.

    스냅샷 행을 지우면 요약/상세가 실시간 스캔 폴백으로 최신 상태를 즉시 보여주고,
    백그라운드 리프레셔가 다음 주기에 스냅샷을 다시 만든다.
    """
    session.execute(
        sa_delete(TestStatusSnapshot).where(
            TestStatusSnapshot.project == project, TestStatusSnapshot.name == name
        )
    )
    session.commit()
    clear_summary_cache()


@mutation_router.delete("/file", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_file(
    code: str = Query(...),
    path: str = Query(...),
    session: Session = Depends(get_session),
) -> None:
    """테스트/실패 테스트/로그 파일 1개를 영구 삭제한다(뷰어 GET /file과 동일한 경로 경계).

    대응 debug 로그도 함께 정리한다. 같은 체크아웃에서 job 실행 중이면 409.
    """
    product = session.scalars(
        select(Product).where(Product.product_code == code)
    ).first()
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    root = workspace.existing_product_checkout(product)
    if root is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없다")
    try:
        raise_if_code_path_busy(session, root)
    except CodePathBusyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    result = test_status_service.delete_test_file(root, product, path)
    if result == "invalid":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "허용되지 않는 경로다")
    if result == "not_found":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없다")
    _invalidate_after_delete(session, product.project, product.name)


@mutation_router.delete("/target")
def delete_target_tests(
    name: str = Query(...),
    path: str = Query(...),
    project: Project = Query(Project.ULYSSES),
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """대상 파일(path)의 테스트를 한꺼번에 삭제한다 — 성공·실패(_Fail)·debug 로그 폴더 전체.

    현황은 (project, name) 그룹 합산이므로 그룹의 모든 프로덕트 체크아웃에서 지운다.
    하나라도 job 실행 중이면 409(아무것도 지우지 않음). 반환: {deleted_files: n}.
    """
    group = list(
        session.scalars(
            select(Product).where(
                Product.project == project.value, Product.name == name
            )
        )
    )
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    try:
        stem = Path(normalize_rel_path(path)).stem
    except PathValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "허용되지 않는 경로다") from exc

    # 삭제 전에 그룹 전체의 busy를 먼저 검사한다 — 일부만 지워지는 부분 삭제 방지
    pairs = []
    for product in group:
        root = workspace.existing_product_checkout(product)
        if root is None:
            continue
        try:
            raise_if_code_path_busy(session, root)
        except CodePathBusyError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        pairs.append((product, root))

    deleted = sum(
        test_status_service.delete_target_tests(root, product, stem)
        for product, root in pairs
    )
    _invalidate_after_delete(session, project.value, name)
    return {"deleted_files": deleted}
