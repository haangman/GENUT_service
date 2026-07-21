"""파일시스템 유틸리티 (서비스 공용)."""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path


def rmtree_force(root: Path) -> None:
    """읽기 전용 파일(Windows의 git 객체 등)도 지우는 관용 rmtree.

    실패해도 예외를 던지지 않는다(best-effort 정리용).
    """

    def _grant_write(func, path, _exc):  # noqa: ANN001
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    try:
        shutil.rmtree(root, onexc=_grant_write)
    except OSError:
        pass
