"""GENUT CLI 실행기(executor) 추상화.

genut_runner는 워크스페이스를 호스트에 준비한 뒤, 실제 CLI 실행을 executor에 위임한다.
executor는 (1) 호스트 경로를 실행 환경 경로로 변환(to_exec_path)하고
(2) argv를 실행(run)한다. 호스트 실행과 Docker 실행을 동일 인터페이스로 다룬다.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

from genut_service.runner import subprocess_util


class HostExecutor:
    """호스트에서 직접 실행. 경로 변환은 항등(절대경로 문자열)."""

    def to_exec_path(self, host_path: Path | str) -> str:
        return str(Path(host_path).resolve())

    def base_python(self) -> str:
        """venv 생성에 쓸 기준 인터프리터(현재 호스트 인터프리터)."""
        return sys.executable

    def venv_python(self, venv_dir: Path | str) -> str:
        """venv 안의 python 실행 경로(OS별 레이아웃).

        **심볼릭 링크를 따라가지 않는다**(`os.path.abspath`, `resolve()` 아님). 리눅스에서
        venv의 `bin/python`은 베이스 인터프리터로의 symlink인데, 이를 resolve하면 베이스
        경로가 되어 pip가 venv가 아닌 베이스(외부 관리, PEP 668) 환경을 대상으로 실행돼
        `externally-managed-environment` 오류가 난다. venv 경로 그대로 실행해야 venv가 활성화된다.
        """
        sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return os.path.abspath(Path(venv_dir) / sub)

    def run(
        self,
        argv: list[str],
        cwd_host: Path,
        timeout: int,
        on_line: Callable[[str], None] | None = None,
    ) -> dict:
        if on_line is not None:
            return subprocess_util.run_streaming(
                argv, cwd=str(cwd_host), timeout=timeout, on_line=on_line
            )
        return subprocess_util.run(argv, cwd=str(cwd_host), timeout=timeout)
