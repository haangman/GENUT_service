"""외부 프로세스 실행 래퍼. 예외 대신 결과 dict을 반환한다."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Callable


def kill_tree(proc: object) -> None:
    """Popen과 그 자식 프로세스 트리를 강제 종료한다(best-effort, 크로스플랫폼).

    run_streaming이 start_new_session=True로 띄우므로 POSIX에서는 프로세스 그룹(setsid)을
    통째로 죽일 수 있고(빌드/컴파일러 등 손자 프로세스 포함), Windows에서는 `taskkill /T`로
    자식 트리까지 정리한다. pid가 없거나 실패하면 부모만 terminate/kill로 폴백한다.
    """
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    if pid is not None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
                return
            os.killpg(os.getpgid(pid), getattr(signal, "SIGKILL", 9))
            return
        except Exception:  # noqa: BLE001 - 이미 죽었거나 권한/플랫폼 문제면 폴백
            pass
    for method in ("terminate", "kill"):
        try:
            getattr(proc, method)()
        except Exception:  # noqa: BLE001
            pass


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
    on_start: Callable[[subprocess.Popen], None] | None = None,
) -> dict:
    """argv를 실행하며 stdout(+stderr)을 줄 단위로 스트리밍한다.

    각 줄이 나올 때마다 on_line(line)을 호출(실시간 로그 기록용)하고, 전체 출력을
    모아 run()과 동일한 형태로 반환한다. stderr는 stdout에 합쳐 시간 순서를 보존한다.
    on_start가 주어지면 프로세스 생성 직후 Popen 핸들로 호출한다(강제 종료 등록용).
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
            # 새 세션/프로세스 그룹으로 띄워 kill_tree가 자식까지 통째로 종료할 수 있게 한다.
            # (POSIX: setsid. Windows에서는 무시되며 taskkill /T가 트리를 정리)
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"success": False, "returncode": None, "stdout": "", "stderr": str(exc)}

    if on_start is not None:
        try:
            on_start(proc)
        except Exception:  # noqa: BLE001 - 등록 콜백 실패가 실행을 막지 않도록
            pass

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
