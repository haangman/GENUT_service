"""프로덕트/GENUT repo의 로컬 체크아웃 관리.

- code_path가 지정되면 그 영속 경로를 코드 위치로 사용한다(절대/상대 모두 허용).
- 요청 페이지(파일트리/compile-check)는 ensure_product_checkout로 코드를 읽되,
  실행 중 작업과 충돌하지 않도록 **이미 받아진 경우 업데이트하지 않는다**(없을 때만 최초 clone).
- 작업 실행 시의 제자리 업데이트는 runner가 git_ops.ensure_checkout로 수행한다.
테스트에서는 ensure_product_checkout를 임시 디렉터리로 대체(monkeypatch)한다.
"""

from __future__ import annotations

from pathlib import Path

from genut_service.config import get_settings
from genut_service.db.models import GenutInstance, Product
from genut_service.runner import git_ops


def product_checkout_root(product_id: int) -> Path:
    """code_path가 없을 때 쓰는 프로덕트 체크아웃 캐시 경로."""
    return Path(get_settings().workspace_root).resolve() / "products" / str(product_id)


def job_log_path(job_id: int) -> Path:
    """job별 전체 진행 로그 파일 경로 (genut_runner의 job_root와 동일 기준)."""
    return Path(get_settings().workspace_root) / f"job_{job_id}" / "job.log"


def resolve_code_path(code_path: str) -> Path:
    """code_path 해석: 절대면 그대로, 상대면 WORKSPACE_ROOT 기준."""
    path = Path(code_path)
    if path.is_absolute():
        return path
    return Path(get_settings().workspace_root) / path


def product_code_dir(product: Product) -> Path:
    """프로덕트 코드 디렉터리: code_path 있으면 그 경로, 없으면 캐시 경로."""
    if product.code_path:
        return resolve_code_path(product.code_path)
    return product_checkout_root(product.id)


def genut_code_dir(genut: GenutInstance) -> Path | None:
    """GENUT 코드 디렉터리: code_path 있으면 그 경로의 GENUT 하위, 없으면 None(임시 clone 사용)."""
    if genut.code_path:
        return resolve_code_path(genut.code_path) / "GENUT"
    return None


def existing_product_checkout(product: Product) -> Path | None:
    """이미 받아진(.git 존재) 프로덕트 코드 경로만 반환한다 — clone 부작용 없음.

    독립 상태 서버의 파일 뷰어처럼 읽기 전용이어야 하는 경로에서 사용한다.
    체크아웃이 없으면 None(호출부가 404 등으로 처리).
    """
    root = product_code_dir(product)
    if (root / ".git").is_dir():
        return root
    return None


def ensure_product_checkout(product: Product) -> Path:
    """요청 페이지용(읽기 전용) 프로덕트 코드 경로를 반환한다.

    code_path가 있으면 그 경로, 없으면 캐시 경로를 사용한다. 이미 받아진(.git 존재)
    경우에는 **업데이트하지 않는다**(실행 중 작업의 reset과 충돌 방지). 없을 때만 clone.
    """
    root = product_code_dir(product)
    if (root / ".git").is_dir():
        return root
    git_ops.clone(product.git_url, product.git_ref, root, timeout=get_settings().git_timeout)
    return root
