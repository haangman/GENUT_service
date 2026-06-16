"""프로덕트 repo의 로컬 체크아웃(캐시) 관리.

파일트리 탐색과 compile_commands.json 읽기에 사용한다. 실제 git clone/update를
수행하며, 테스트에서는 ensure_product_checkout를 임시 디렉터리로 대체(monkeypatch)한다.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from genut_service.config import get_settings
from genut_service.db.models import Product
from genut_service.runner import git_ops


def product_checkout_root(product_id: int) -> Path:
    """프로덕트 체크아웃 캐시 경로."""
    return Path(get_settings().workspace_root).resolve() / "products" / str(product_id)


def job_log_path(job_id: int) -> Path:
    """job별 전체 진행 로그 파일 경로 (genut_runner의 job_root와 동일 기준)."""
    return Path(get_settings().workspace_root) / f"job_{job_id}" / "job.log"


def ensure_product_checkout(product: Product) -> Path:
    """프로덕트 repo를 clone(없으면)하거나 최신으로 업데이트하고 경로를 반환한다.

    기본 브랜치 이름에 의존하지 않도록 git_ops.clone(브랜치 비의존 + 관용적 checkout)을
    사용한다. 업데이트는 fetch + reset --hard로 시도하되 실패해도 캐시를 그대로 쓴다.
    """
    root = product_checkout_root(product.id)
    timeout = get_settings().git_timeout
    if (root / ".git").is_dir():
        fetch = subprocess.run(
            ["git", "-C", str(root), "fetch", "origin"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
        if fetch.returncode == 0:
            subprocess.run(
                ["git", "-C", str(root), "reset", "--hard", f"origin/{product.git_ref}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
        return root
    # 깨진 캐시가 있으면 정리 후 새로 clone
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    git_ops.clone(product.git_url, product.git_ref, root, timeout=timeout)
    return root
