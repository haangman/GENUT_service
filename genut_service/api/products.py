"""프로덕트 등록 API."""

from __future__ import annotations

from fnmatch import fnmatch

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import PageParams, get_session
from genut_service.schemas.common import Page
from genut_service.schemas.job import JobRead
from genut_service.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductUpdate,
    TargetFileItem,
    TargetFilesRequest,
    TargetFilesResponse,
)
from genut_service.services import (
    auto_product_service,
    compile_db_service,
    product_service,
    test_status_service,
)
from genut_service.services.auto_product_service import AutoProductError

router = APIRouter(prefix="/api/products", tags=["products"])


@router.post("/target-files", response_model=TargetFilesResponse)
def preview_target_files(body: TargetFilesRequest) -> TargetFilesResponse:
    """폼 단계용: 로컬 code_path의 compile_commands.json에서 기본 필터를 적용한 대상 파일 후보를
    반환한다. 각 후보에 제외 글롭 매칭 여부(excluded_by_pattern)를 표시한다(목록은 제외 전 전체)."""
    if not body.code_path.strip() or not body.compile_db_rel.strip():
        return TargetFilesResponse(files=[])
    root = workspace.resolve_code_path(body.code_path)
    rels = compile_db_service.list_files(root, body.compile_db_rel)
    candidates = test_status_service.candidate_target_files(rels)
    globs = [g for g in body.exclude_globs if g and g.strip()]
    files = [
        TargetFileItem(
            path=rel,
            excluded_by_pattern=any(fnmatch(rel, glob) for glob in globs),
        )
        for rel in candidates
    ]
    return TargetFilesResponse(files=files)


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductCreate, session: Session = Depends(get_session)) -> ProductRead:
    try:
        product = product_service.create_product(session, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 프로덕트 이름이다")
    return ProductRead.model_validate(product)


@router.post("/auto", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_auto_product(
    data: ProductCreate, session: Session = Depends(get_session)
) -> ProductRead:
    """자동 실행 프로덕트 1개를 만들고 테스트 출력 폴더에 CMakeLists 스캐폴딩을 생성한다."""
    try:
        product = auto_product_service.create_auto_product(session, data)
    except AutoProductError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return ProductRead.model_validate(product)


@router.put("/{product_id}/auto", response_model=ProductRead)
def update_auto_product(
    product_id: int, data: ProductCreate, session: Session = Depends(get_session)
) -> ProductRead:
    """자동 실행 프로덕트를 수정하고 갱신된 정보/파일 목록으로 스캐폴딩을 재생성한다."""
    try:
        product = auto_product_service.update_auto_product(session, product_id, data)
    except AutoProductError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return ProductRead.model_validate(product)


@router.post(
    "/{product_id}/auto/run",
    response_model=list[JobRead],
    status_code=status.HTTP_201_CREATED,
)
def run_auto_now(product_id: int, session: Session = Depends(get_session)) -> list[JobRead]:
    """주기와 무관하게 auto 사이클(변경 감지→누락 스캔)을 지금 큐잉한다.

    이전 사이클의 준비 job이 아직 대기/실행 중이면 중복을 만들지 않고 409를 반환한다.
    실행 자체는 백그라운드 스케줄러가 다음 tick에 집어 처리한다.
    """
    from genut_service.db.models import Job, Product
    from genut_service.scheduler import auto_tick

    product = session.get(Product, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    if not product.auto_run:
        raise HTTPException(status.HTTP_409_CONFLICT, "자동 실행 프로덕트가 아니다")
    job_ids = auto_tick.enqueue_cycle_now(session, product)
    if not job_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "이미 진행 중인 자동 실행이 있다 (완료 후 다시 시도)"
        )
    jobs = [session.get(Job, job_id) for job_id in job_ids]
    return [JobRead.model_validate(job) for job in jobs if job is not None]


@router.get("", response_model=Page[ProductRead])
def list_products(
    params: PageParams = Depends(),
    q: str | None = Query(None),
    session: Session = Depends(get_session),
) -> Page[ProductRead]:
    items, total = product_service.list_products(session, params.page, params.page_size, q)
    return Page[ProductRead](
        items=[ProductRead.model_validate(item) for item in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> ProductRead:
    product = product_service.get_product(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return ProductRead.model_validate(product)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, data: ProductUpdate, session: Session = Depends(get_session)
) -> ProductRead:
    try:
        product = product_service.update_product(session, product_id, data)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 존재하는 프로덕트 이름이다")
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    return ProductRead.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, session: Session = Depends(get_session)) -> None:
    try:
        deleted = product_service.delete_product(session, product_id)
    except product_service.ProductInUseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
