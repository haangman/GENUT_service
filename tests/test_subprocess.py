"""subprocess_util.run_streaming 동작 테스트."""

from __future__ import annotations

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
