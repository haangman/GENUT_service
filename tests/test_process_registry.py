"""실행 중 서브프로세스 강제 종료 레지스트리 테스트."""

from __future__ import annotations

import subprocess
import sys

from genut_service.runner import process_registry


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])


def test_cancel_kills_registered_process() -> None:
    proc = _spawn_sleeper()
    try:
        process_registry.register(101, proc)
        assert process_registry.cancel(101) is True
        proc.wait(timeout=5)
        assert proc.returncode is not None  # 죽었다
    finally:
        process_registry.unregister(101)
        if proc.poll() is None:
            proc.kill()


def test_register_after_cancel_kills_immediately() -> None:
    # proc 등록 전에 취소가 먼저 요청된 레이스 상황
    assert process_registry.cancel(102) is False  # 실행 중 proc 없음
    assert process_registry.is_canceled(102) is True
    proc = _spawn_sleeper()
    try:
        process_registry.register(102, proc)  # 등록 즉시 종료돼야 함
        proc.wait(timeout=5)
        assert proc.returncode is not None
    finally:
        process_registry.unregister(102)
        if proc.poll() is None:
            proc.kill()


def test_cancel_without_process_returns_false() -> None:
    assert process_registry.cancel(103) is False
    process_registry.unregister(103)


def test_unregister_clears_canceled_flag() -> None:
    process_registry.cancel(104)
    assert process_registry.is_canceled(104) is True
    process_registry.unregister(104)
    assert process_registry.is_canceled(104) is False
