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

    def base_python(self) -> str:
        """venv 생성에 쓸 기준 인터프리터(컨테이너 PATH의 python)."""
        return "python"

    def venv_python(self, venv_dir: Path | str) -> str:
        """venv 안의 python 컨테이너 경로(리눅스 레이아웃).

        leaf(`bin/python`)는 컨테이너 베이스 python으로의 symlink이므로 resolve하면 안 된다
        (호스트에서 relative_to 실패/베이스 환경 지목). 디렉터리 컨테이너 경로 + `/bin/python`로 만든다.
        """
        return f"{self.to_exec_path(venv_dir)}/bin/python"

    def run(
        self,
        argv: list[str],
        cwd_host: Path,
        timeout: int,
        on_line: Callable[[str], None] | None = None,
        on_start: Callable[[object], None] | None = None,
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
            return subprocess_util.run_streaming(
                cmd, timeout=timeout, on_line=on_line, on_start=on_start
            )
        return subprocess_util.run(cmd, timeout=timeout)
