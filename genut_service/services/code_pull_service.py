"""프로덕트 코드 저장 경로로 git 코드를 받아오는(다운로드) 서비스 (FastAPI 비의존).

폼 값(git_url/git_ref/code_path) 기반이라 저장 전 신규 등록 중에도 동작한다.
같은 코드 디렉터리를 쓰는 프로덕트의 job이 실행 중이면 git reset 경합을 막기 위해
거부한다(CodePathBusyError). busy 검사 후 clone 중 job이 시작되는 TOCTOU 창은
요청 페이지의 ensure_product_checkout와 동일한 성질로 수용한다.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.db.models import Job, Product, ProductLock
from genut_service.enums import PREP_KINDS, JobStatus
from genut_service.runner import git_ops
from genut_service.schemas.product import PullCodeRequest, PullCodeResponse

_PREP_KIND_VALUES = tuple(kind.value for kind in PREP_KINDS)


class CodePathBusyError(Exception):
    """대상 경로를 쓰는 프로덕트의 job이 실행 중이라 다운로드할 수 없다."""


def _normcase(path: Path) -> str:
    """경로 비교 키 — Windows 대소문자 차이로 busy 검사가 새지 않게 정규화한다."""
    return os.path.normcase(str(path.resolve()))


def _busy_products(session: Session) -> list[Product]:
    """락 보유(GENUT 실행 중) 또는 준비 job 실행 중인 프로덕트 목록."""
    ids = set(session.scalars(select(ProductLock.product_id)))
    ids |= set(
        session.scalars(
            select(Job.product_id).where(
                Job.status == JobStatus.RUNNING.value,
                Job.kind.in_(_PREP_KIND_VALUES),
            )
        )
    )
    if not ids:
        return []
    return list(session.scalars(select(Product).where(Product.id.in_(ids))))


def raise_if_code_path_busy(session: Session, dest: Path) -> None:
    """dest를 코드 디렉터리로 쓰는 프로덕트의 job이 실행 중이면 CodePathBusyError.

    다운로드(git reset)·폼 명령 실행이 실행 중 job과 같은 체크아웃에서 경합하지 않게
    하는 공용 가드다.
    """
    dest_key = _normcase(dest)
    for product in _busy_products(session):
        if _normcase(workspace.product_code_dir(product)) == dest_key:
            raise CodePathBusyError(
                f"프로덕트 '{product.name}'의 작업이 실행 중이라 이 경로를 사용할 수 없다"
            )


def pull_code(session: Session, req: PullCodeRequest) -> PullCodeResponse:
    """code_path로 git 코드를 받아온다 — 없으면 clone, 있으면 fetch+reset 제자리 업데이트.

    git 실패는 GitError를 그대로 전파한다(호출부가 HTTP로 매핑). strict 모드로 실행해
    제자리 업데이트의 fetch/reset 실패도 성공으로 오인하지 않는다.
    """
    dest = workspace.resolve_code_path(req.code_path)
    raise_if_code_path_busy(session, dest)

    existed = (dest / ".git").is_dir()
    preserve = [req.out_tests_rel] if req.out_tests_rel else []
    git_ops.ensure_checkout(
        req.git_url,
        req.git_ref,
        dest,
        timeout=get_settings().git_timeout,
        preserve=preserve,
        strict=True,
    )
    return PullCodeResponse(
        path=str(dest),
        detail="업데이트 완료" if existed else "클론 완료",
        # 폼 로그창용: runner가 job 로그에 남기는 것과 같은 최근 커밋 정보
        log=f"최근 커밋:\n{git_ops.recent_log(dest)}",
    )
