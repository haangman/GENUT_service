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


# 손자를 띄워 stdout 파이프를 물려준 뒤 자신은 바로 종료하는 스크립트 —
# "직계 자식은 끝났지만 손자가 파이프를 쥐고 계속 쓰는" 상황(pip 잔존 빌드 등) 재현용.
_ORPHAN_PIPE_HOLDER = (
    "import subprocess, sys\n"
    "child = subprocess.Popen([sys.executable, '-c', "
    "\"import time\\nwhile True:\\n    print('orphan-line', flush=True)\\n    time.sleep(0.05)\"])\n"
    "print('GRANDCHILD', child.pid, flush=True)\n"
)


def test_run_streaming_finishes_promptly_when_grandchild_holds_pipe() -> None:
    """직계 자식이 끝나면 손자가 파이프를 쥐고 있어도 곧 반환하고, 반환 후에는
    콜백이 더 이상 불리지 않으며(다음 단계와 로그/세션이 섞이는 것 방지),
    잔존 손자도 정리된다."""
    lines: list[str] = []
    start = time.time()
    result = subprocess_util.run_streaming(
        [sys.executable, "-c", _ORPHAN_PIPE_HOLDER], timeout=60, on_line=lines.append
    )
    elapsed = time.time() - start

    assert result["success"] is True  # 직계 자식은 정상 종료(rc=0)
    assert elapsed < 30  # 손자가 살아 있어도 join 유예 안에 반환한다

    grandchild_pid = int(
        next(line for line in lines if line.startswith("GRANDCHILD")).split()[1]
    )
    # 반환 후에는 잔존 reader가 콜백을 더 호출하지 않는다
    count_at_return = len(lines)
    time.sleep(1.0)
    assert len(lines) == count_at_return
    # 잔존 손자는 정리된다(그룹 종료 또는 파이프 단절로 곧 죽는다)
    assert _wait_dead(grandchild_pid), "파이프를 쥔 손자가 살아남았다"


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


def test_run_decodes_output_with_given_encoding() -> None:
    """run(encoding=...)이 자식 출력의 비-UTF-8 인코딩을 올바르게 디코딩한다.

    Windows 폼 명령 실행(cmd /c)의 네이티브 출력은 콘솔 OEM 코드페이지(한글 cp949)라
    utf-8 고정 디코딩이면 한글 경로/메시지가 U+FFFD로 깨진다 — 회귀 가드.
    """
    code = "import sys; sys.stdout.buffer.write('한글 경로'.encode('cp949'))"
    result = subprocess_util.run([sys.executable, "-c", code], encoding="cp949")
    assert result["success"]
    assert result["stdout"] == "한글 경로"

    garbled = subprocess_util.run([sys.executable, "-c", code])  # 기본 utf-8
    assert "�" in garbled["stdout"]
