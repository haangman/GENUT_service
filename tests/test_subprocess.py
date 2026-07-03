"""subprocess_util.run_streaming 동작 테스트."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from genut_service.runner import subprocess_util

# 손자 프로세스(60초 sleep)를 띄워 pid를 출력한 뒤 자신도 오래 잠드는 스크립트 —
# 타임아웃 처리에서 트리 전체(손자 포함)가 죽는지 검증하는 데 쓴다.
_GRANDCHILD_SPAWNER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "print(child.pid, flush=True)\n"
    "time.sleep(60)\n"
)


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _wait_dead(pid: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.2)
    return False


def test_run_streaming_calls_on_line_per_line() -> None:
    lines: list[str] = []
    code = "for i in range(3): print('line', i)"
    result = subprocess_util.run_streaming([sys.executable, "-c", code], on_line=lines.append)
    assert result["success"] is True
    assert lines == ["line 0", "line 1", "line 2"]
    assert "line 2" in result["stdout"]


def test_run_streaming_nonzero_exit() -> None:
    result = subprocess_util.run_streaming([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert result["success"] is False
    assert result["returncode"] == 3


def test_run_timeout_kills_grandchildren() -> None:
    """run 타임아웃 시 직계 자식뿐 아니라 손자 프로세스까지 종료된다."""
    result = subprocess_util.run([sys.executable, "-c", _GRANDCHILD_SPAWNER], timeout=3)
    assert result["success"] is False
    assert "timeout" in result["stderr"]
    grandchild_pid = int(result["stdout"].strip().splitlines()[0])
    assert _wait_dead(grandchild_pid), "손자 프로세스가 살아남았다(고아화)"


def test_run_streaming_timeout_kills_grandchildren() -> None:
    """run_streaming 타임아웃 시 kill_tree로 손자 프로세스까지 종료된다."""
    lines: list[str] = []
    result = subprocess_util.run_streaming(
        [sys.executable, "-c", _GRANDCHILD_SPAWNER], timeout=3, on_line=lines.append
    )
    assert result["success"] is False
    assert "timeout" in result["stderr"]
    grandchild_pid = int(lines[0])
    assert _wait_dead(grandchild_pid), "손자 프로세스가 살아남았다(고아화)"


def test_kill_tree_terminates_running_process() -> None:
    """kill_tree는 실행 중인 프로세스를 (트리째) 강제 종료한다."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    assert proc.poll() is None  # 살아 있음
    subprocess_util.kill_tree(proc)
    proc.wait(timeout=10)  # 곧 죽어야 한다 — 타임아웃 안 나면 성공
    assert proc.poll() is not None


def test_kill_tree_fallback_without_pid() -> None:
    """pid가 없으면 부모 terminate/kill로 폴백한다(가짜 핸들)."""
    calls: list[str] = []

    class _Fake:
        pid = None

        def terminate(self) -> None:
            calls.append("terminate")

        def kill(self) -> None:
            calls.append("kill")

    subprocess_util.kill_tree(_Fake())
    assert calls  # terminate/kill 중 하나 이상 호출됨
