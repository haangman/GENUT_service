"""외부 프로세스 실행 래퍼. 예외 대신 결과 dict을 반환한다."""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable


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


def run_streaming(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict | None = None,
    on_line: Callable[[str], None] | None = None,
) -> dict:
    """argv를 실행하며 stdout(+stderr)을 줄 단위로 스트리밍한다.

    각 줄이 나올 때마다 on_line(line)을 호출(실시간 로그 기록용)하고, 전체 출력을
    모아 run()과 동일한 형태로 반환한다. stderr는 stdout에 합쳐 시간 순서를 보존한다.
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return {"success": False, "returncode": None, "stdout": "", "stderr": str(exc)}

    lines: list[str] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            if on_line is not None:
                try:
                    on_line(line)
                except Exception:  # noqa: BLE001 - 로그 콜백 실패가 실행을 막지 않도록
                    pass

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=2)
        return {
            "success": False,
            "returncode": None,
            "stdout": "\n".join(lines),
            "stderr": f"timeout after {timeout}s",
        }
    reader.join(timeout=5)
    rc = proc.returncode
    return {"success": rc == 0, "returncode": rc, "stdout": "\n".join(lines), "stderr": ""}
