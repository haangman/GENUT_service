"""M8: DockerExecutor 경로 매핑 및 docker run 명령 구성 (docker 불필요, 기본 실행)."""

from __future__ import annotations

from pathlib import Path

import pytest

from genut_service.docker.client import DockerExecutor
from genut_service.runner import subprocess_util


def test_to_exec_path_maps_into_container(tmp_path: Path) -> None:
    job_root = tmp_path / "job_1"
    (job_root / "product" / "src").mkdir(parents=True)
    executor = DockerExecutor("img", job_root)
    assert executor.to_exec_path(job_root) == "/work"
    assert executor.to_exec_path(job_root / "product" / "src" / "a.cpp") == "/work/product/src/a.cpp"


def test_run_builds_docker_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    job_root = tmp_path / "job_1"
    (job_root / "genut").mkdir(parents=True)
    captured: dict = {}

    def fake_run(argv, cwd=None, timeout=600, env=None):  # noqa: ANN001
        captured["argv"] = argv
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(subprocess_util, "run", fake_run)
    executor = DockerExecutor("genut-runner:latest", job_root, cpus=2, memory="2g")
    executor.run(["python", "fake_genut.py", "--x"], job_root / "genut", 100)

    argv = captured["argv"]
    assert argv[:3] == ["docker", "run", "--rm"]
    assert f"{job_root.resolve()}:/work" in argv
    assert "/work/genut" in argv
    assert "genut-runner:latest" in argv
    assert argv[-3:] == ["python", "fake_genut.py", "--x"]
