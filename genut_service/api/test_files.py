"""프로덕트별 테스트 파일 등록/다운로드 API.

product_name은 공백/괄호/한글/슬래시 등을 포함할 수 있어 path 파라미터 대신
query/body로 받는다(URL 인코딩 함정 회피).
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.api.deps import get_session
from genut_service.schemas.test_files import (
    TestFileAddRequest,
    TestFileDownloadRequest,
    TestFileEntry,
    TestFileRemoveRequest,
)
from genut_service.services import product_service, test_file_service

router = APIRouter(prefix="/api/test-files", tags=["test-files"])


@router.get("", response_model=list[TestFileEntry])
def list_test_files(
    product_name: str = Query(...),
    session: Session = Depends(get_session),
) -> list[TestFileEntry]:
    rows = test_file_service.list_registered(session, product_name)
    return [TestFileEntry.model_validate(row) for row in rows]


@router.post("", response_model=list[TestFileEntry], status_code=status.HTTP_201_CREATED)
def add_test_files(
    body: TestFileAddRequest,
    session: Session = Depends(get_session),
) -> list[TestFileEntry]:
    rows = test_file_service.add_registered(session, body.product_name, body.rel_paths)
    return [TestFileEntry.model_validate(row) for row in rows]


@router.delete("")
def remove_test_files(
    body: TestFileRemoveRequest,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    removed = test_file_service.remove_registered(
        session, body.product_name, body.rel_paths
    )
    return {"removed": removed}


@router.post("/download")
def download_test_files(
    body: TestFileDownloadRequest,
    session: Session = Depends(get_session),
) -> Response:
    product = product_service.get_product(session, body.product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로덕트를 찾을 수 없다")
    root = workspace.ensure_product_checkout(product)
    data = test_file_service.build_zip(root, body.rel_paths)
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "다운로드할 파일이 없다")
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": _content_disposition(f"{product.name}_tests.zip")},
    )


def _content_disposition(filename: str) -> str:
    """비-ASCII 파일명을 안전하게 담는 Content-Disposition 값.

    헤더는 latin-1로 인코딩되므로, ASCII 폴백(filename=)과 RFC 5987(filename*=)을
    함께 제공해 한글 등 파일명을 깨지지 않게 한다.
    """
    ascii_fallback = filename.encode("ascii", "ignore").decode() or "tests.zip"
    quoted = quote(filename)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quoted}"
