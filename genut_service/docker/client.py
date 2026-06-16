"""Docker 실행기. job 워크스페이스를 컨테이너에 bind-mount하여 GENUT CLI를 실행한다."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

from genut_service.runner import subprocess_util


def is_docker_available() -> bool:
    """docker CLI가 있고 데몬에 접근 가능한지."""
    if shutil.which("docker") is None:
        return False
    return subprocess_util.run(["docker", "info"], timeout=20)["success"]


class DockerExecutor:
    """job_root를 컨테이너 container_root에 마운트하고 그 안에서 실행한다."""

    def __init__(
        self,
        image: str,
        job_root: Path | str,
        container_root: str = "/work",
        cpus: float | None = None,
        memory: str | None = None,
        docker_bin: str = "docker",
    ):
        self.image = image
        self.job_root = Path(job_root).resolve()
        self.container_root = container_root.rstrip("/")
        self.cpus = cpus
        self.memory = memory
        self.docker_bin = docker_bin

    def to_exec_path(self, host_path: Path | str) -> str:
        rel = Path(host_path).resolve().relative_to(self.job_root).as_posix()
        return self.container_root if rel == "." else f"{self.container_root}/{rel}"

    def run(
        self,
        argv: list[str],
        cwd_host: Path,
        timeout: int,
        on_line: Callable[[str], None] | None = None,
    ) -> dict:
        cmd = [
            self.docker_bin,
            "run",
            "--rm",
            "-v",
            f"{self.job_root}:{self.container_root}",
            "-w",
            self.to_exec_path(cwd_host),
        ]
        if self.cpus:
            cmd += ["--cpus", str(self.cpus)]
        if self.memory:
            cmd += ["--memory", str(self.memory)]
        cmd += [self.image, *argv]
        if on_line is not None:
            return subprocess_util.run_streaming(cmd, timeout=timeout, on_line=on_line)
        return subprocess_util.run(cmd, timeout=timeout)
