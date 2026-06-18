"""subprocess_util.run_streaming 동작 테스트."""

from __future__ import annotations

import subprocess
import sys

from genut_service.runner import subprocess_util


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
