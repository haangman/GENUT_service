"""프로덕트별 테스트 파일 등록/다운로드 비즈니스 로직 (FastAPI 비의존).

같은 이름의 프로덕트는 코드를 공유하므로 등록 리스트는 product_name으로 그룹핑한다.
rel_path는 프로덕트 코드 체크아웃 루트 기준 상대경로(POSIX)로 정규화해 저장한다.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service.db.models import ProductTestFile
from genut_service.paths import PathValidationError, normalize_rel_path


def list_registered(session: Session, product_name: str) -> list[ProductTestFile]:
    """프로덕트(이름)에 등록된 테스트 파일을 rel_path 오름차순으로 반환."""
    return list(
        session.scalars(
            select(ProductTestFile)
            .where(ProductTestFile.product_name == product_name)
            .order_by(ProductTestFile.rel_path)
        ).all()
    )


def add_registered(
    session: Session, product_name: str, rel_paths: list[str]
) -> list[ProductTestFile]:
    """rel_paths를 등록 리스트에 추가한다(정규화·중복 제거). 추가 후 전체 목록을 반환.

    잘못된 경로(`..` 등)는 건너뛴다. 이미 등록된 경로는 무시한다(유일 제약).
    """
    existing = {
        row.rel_path for row in list_registered(session, product_name)
    }
    seen: set[str] = set()
    for raw in rel_paths:
        try:
            rel = normalize_rel_path(raw)
        except PathValidationError:
            continue
        if not rel or rel in existing or rel in seen:
            continue
        seen.add(rel)
        session.add(ProductTestFile(product_name=product_name, rel_path=rel))
    session.commit()
    return list_registered(session, product_name)


def remove_registered(
    session: Session, product_name: str, rel_paths: list[str]
) -> int:
    """rel_paths를 등록 리스트에서 제거한다. 제거한 건수를 반환."""
    targets = {normalize_rel_path(p) for p in rel_paths if p.strip()}
    removed = 0
    for row in list_registered(session, product_name):
        if row.rel_path in targets:
            session.delete(row)
            removed += 1
    session.commit()
    return removed


def _safe_target(root: Path, rel: str) -> Path | None:
    """rel을 root 기준으로 안전하게 해석한다. root 밖이거나 파일이 아니면 None."""
    try:
        rel_norm = normalize_rel_path(rel)
    except PathValidationError:
        return None
    if not rel_norm:
        return None
    root_resolved = root.resolve()
    target = (root_resolved / rel_norm).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        return None
    return target if target.is_file() else None


def build_zip(root: Path, rel_paths: list[str]) -> bytes:
    """root 하위의 rel_paths 파일들을 zip 바이트로 묶는다.

    root 밖을 가리키거나 존재하지 않는 경로는 건너뛴다(부분 실패 허용). 압축 안에
    들어간 파일이 하나도 없으면 빈 zip이 아니라 b""를 반환한다(호출부에서 404 처리).
    """
    added = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for raw in rel_paths:
            target = _safe_target(root, raw)
            if target is None:
                continue
            arcname = normalize_rel_path(raw)
            archive.write(target, arcname=arcname)
            added += 1
    if added == 0:
        return b""
    return buffer.getvalue()
