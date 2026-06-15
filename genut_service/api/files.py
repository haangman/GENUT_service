"""파일트리 탐색 및 compile_commands.json 포함 검사 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.schemas.filetree import (
    CompileCheckRequest,
    CompileCheckResponse,
    TreeEntry,
    TreeResponse,
)
from genut_service.services import compile_db_service, filetree_service, product_service

router = APIRouter(prefix="/api/products", tags=["files"])


@router.get("/{product_id}/tree", response_model=TreeResponse)
def get_tree(
    product_id: int,
    path: str = Query(""),
    session: Session = Depends(get_session),
) -> TreeResponse:
    product = product_service.get_product(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    root = workspace.ensure_product_checkout(product)
    try:
        entries = filetree_service.list_dir(root, path)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "경로를 찾을 수 없다")
    return TreeResponse(entries=[TreeEntry(**entry) for entry in entries])


@router.post("/{product_id}/compile-check", response_model=CompileCheckResponse)
def compile_check(
    product_id: int,
    body: CompileCheckRequest,
    session: Session = Depends(get_session),
) -> CompileCheckResponse:
    product = product_service.get_product(session, product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    root = workspace.ensure_product_checkout(product)
    included, excluded = compile_db_service.split_inclusion(
        root, product.compile_db_rel, body.files
    )
    return CompileCheckResponse(included=included, excluded=excluded)
