"""외부 프로세스 실행 래퍼. 예외 대신 결과 dict을 반환한다."""

from __future__ import annotations

import subprocess


def run(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict | None = None,
) -> dict:
    """argv를 실행하고 {success, returncode, stdout, stderr}를 반환한다."""
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"timeout after {timeout}s",
        }
    except FileNotFoundError as exc:
        return {"success": False, "returncode": None, "stdout": "", "stderr": str(exc)}
