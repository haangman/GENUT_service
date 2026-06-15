"""프로덕트 repo의 로컬 체크아웃(캐시) 관리.

파일트리 탐색과 compile_commands.json 읽기에 사용한다. 실제 git clone/update를
수행하며, 테스트에서는 ensure_product_checkout를 임시 디렉터리로 대체(monkeypatch)한다.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from genut_service.config import get_settings
from genut_service.db.models import Product


def product_checkout_root(product_id: int) -> Path:
    """프로덕트 체크아웃 캐시 경로."""
    return Path(get_settings().workspace_root).resolve() / "products" / str(product_id)


def ensure_product_checkout(product: Product) -> Path:
    """프로덕트 repo를 clone(없으면)하거나 최신으로 업데이트하고 경로를 반환한다."""
    root = product_checkout_root(product.id)
    timeout = get_settings().git_timeout
    if (root / ".git").is_dir():
        subprocess.run(
            ["git", "-C", str(root), "fetch", "origin", product.git_ref],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
        subprocess.run(
            ["git", "-C", str(root), "reset", "--hard", f"origin/{product.git_ref}"],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--branch", product.git_ref, product.git_url, str(root)],
            check=True, capture_output=True, text=True, timeout=timeout,
        )
    return root
