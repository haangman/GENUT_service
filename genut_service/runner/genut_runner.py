"""job 1건을 실행하는 오케스트레이션.

워크스페이스 준비(product clone + patch, GENUT clone) → .env 조립 →
file-list 작성 → 경로를 실행 환경(executor) 기준으로 변환 → GENUT CLI 실행 → 결과 수집.

CLI 실행은 executor에 위임한다(호스트=HostExecutor, 컨테이너=DockerExecutor).
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from genut_service import workspace
from genut_service.db.models import GenutInstance, Job, Product
from genut_service.paths import normalize_rel_path
from genut_service.runner import env_builder, git_ops
from genut_service.runner.executors import HostExecutor


# 로그에 노출하면 안 되는 .env 키 값(마스킹 대상)
_SECRET_ENV_KEYS = {"DS_ASSIST_CREDENTIAL_KEY"}

# run_command 선행 토큰이 python 인터프리터인지 판단할 때 쓰는 이름들
_PYTHON_NAMES = {"python", "python3", "python.exe", "python3.exe", "py", "py.exe"}


class VenvError(RuntimeError):
    """GENUT 가상환경(.venv) 준비 실패."""


def _masked_env_text(env: dict[str, str]) -> str:
    """.env 내용을 텍스트로. 비밀 키 값은 마스킹한다."""
    return "\n".join(
        f"{key}={'********' if key in _SECRET_ENV_KEYS else value}"
        for key, value in env.items()
    )


def _is_python_token(token: str) -> bool:
    base = Path(token).name.lower()
    return base in _PYTHON_NAMES or base.startswith("python")


def _with_venv_python(run_head: list[str], venv_python: str) -> list[str]:
    """run_command의 선행 인터프리터(python류)를 venv python으로 치환한다.

    선행 토큰이 python이 아니면(예: 콘솔 스크립트) 그대로 둔다.
    """
    if run_head and _is_python_token(run_head[0]):
        return [venv_python, *run_head[1:]]
    return run_head


def _prepare_venv(executor, genut_dir: Path, *, timeout: int, ev, stream: bool) -> str:
    """genut_dir/.venv 가상환경을 만들고 requirements.txt를 설치한 뒤 venv python 경로 반환.

    executor를 통해 실행하므로 호스트/Docker 모두 동일하게 동작한다.
    """
    venv_dir = genut_dir / ".venv"
    venv_python = executor.venv_python(venv_dir)
    on_line = (lambda line: ev("venv", "info", line)) if stream else None

    ev("venv", "info", f".venv 생성/갱신: {executor.to_exec_path(venv_dir)}")
    res = executor.run(
        [executor.base_python(), "-m", "venv", executor.to_exec_path(venv_dir)],
        genut_dir,
        timeout,
        on_line=on_line,
    )
    if not res["success"]:
        raise VenvError(f".venv 생성 실패: {(res.get('stderr') or res.get('stdout') or '')[:500]}")

    req = genut_dir / "requirements.txt"
    if req.is_file():
        ev("venv", "info", "requirements.txt 설치")
        res = executor.run(
            [venv_python, "-m", "pip", "install", "-r", executor.to_exec_path(req)],
            genut_dir,
            timeout,
            on_line=on_line,
        )
        if not res["success"]:
            raise VenvError(
                f"requirements 설치 실패: {(res.get('stderr') or res.get('stdout') or '')[:500]}"
            )
    else:
        ev("venv", "info", "requirements.txt 없음 — 설치 생략")

    ev("venv", "info", f"가상환경(.venv) 진입: {venv_python}")
    return venv_python


@dataclass
class RunResult:
    success: bool
    returncode: int | None
    stdout: str
    stderr: str
    result_summary: str | None
    generated_files: list[str] = field(default_factory=list)
    out_dir: str = ""


def run(
    job: Job,
    product: Product,
    genut: GenutInstance,
    *,
    workspace_root: str,
    debug: bool = True,
    enable_assure: bool = False,
    genut_timeout: int = 1800,
    git_timeout: int = 300,
    use_venv: bool = False,
    make_executor: Callable[[Path], object] | None = None,
    on_event: Callable[[str, str, str], None] | None = None,
) -> RunResult:
    def _ev(phase: str, level: str, message: str) -> None:
        if on_event is not None:
            try:
                on_event(phase, level, message)
            except Exception:  # noqa: BLE001
                pass

    job_root = Path(workspace_root) / f"job_{job.id}"
    job_root.mkdir(parents=True, exist_ok=True)

    # 1) 프로덕트 코드 확보 (code_path 있으면 영속 경로 제자리 업데이트, 없으면 임시 clone)
    #    + 순서대로 patch 멱등 적용. (PatchError/GitError는 호출자가 처리)
    if product.code_path:
        product_dir = workspace.resolve_code_path(product.code_path)
        _ev("clone", "info", f"프로덕트 업데이트(영속): {product_dir} ← {product.git_url} ({product.git_ref})")
        git_ops.ensure_checkout(product.git_url, product.git_ref, product_dir, timeout=git_timeout)
    else:
        product_dir = job_root / "product"
        _ev("clone", "info", f"프로덕트 clone(임시): {product.git_url} ({product.git_ref})")
        git_ops.clone(product.git_url, product.git_ref, product_dir, timeout=git_timeout)
    _ev("clone", "info", f"프로덕트 git log:\n{git_ops.recent_log(product_dir, timeout=git_timeout)}")
    for patch in sorted(product.patches, key=lambda p: p.order_index):
        _ev("patch", "info", f"patch 적용: {patch.name}")
        git_ops.apply_patch(str(product_dir), patch.content, timeout=git_timeout)

    # 2) GENUT 코드 확보 (code_path 있으면 영속 경로 제자리 업데이트, 없으면 임시 clone)
    if genut.code_path:
        genut_dir = workspace.resolve_code_path(genut.code_path)
        _ev("clone", "info", f"GENUT 업데이트(영속): {genut_dir} ← {genut.repo_url} ({genut.repo_ref})")
        git_ops.ensure_checkout(genut.repo_url, genut.repo_ref, genut_dir, timeout=git_timeout)
    else:
        genut_dir = job_root / "genut"
        _ev("clone", "info", f"GENUT clone(임시): {genut.repo_url} ({genut.repo_ref})")
        git_ops.clone(genut.repo_url, genut.repo_ref, genut_dir, timeout=git_timeout)
    _ev("clone", "info", f"GENUT git log:\n{git_ops.recent_log(genut_dir, timeout=git_timeout)}")

    # 3) .env 조립 (GENUT 작업 디렉터리에 기록)
    env_dict = env_builder.build_env(product, genut)
    env_builder.write_env_file(genut_dir / ".env", env_dict)

    # 4) 실행기 선택 (호스트=항등 경로, Docker=컨테이너 경로)
    executor = (make_executor or (lambda _root: HostExecutor()))(job_root)

    # 5) 호스트 절대경로 계산 후 실행 환경 경로로 변환
    compile_db_abs = (product_dir / normalize_rel_path(product.compile_db_rel)).resolve()
    out_abs = (product_dir / normalize_rel_path(product.out_tests_rel)).resolve()
    out_abs.mkdir(parents=True, exist_ok=True)

    filelist_path = job_root / "filelist.txt"
    exec_files = [
        executor.to_exec_path((product_dir / normalize_rel_path(f)).resolve())
        for f in job.file_list
    ]
    filelist_path.write_text(
        "\n".join(exec_files) + ("\n" if exec_files else ""), encoding="utf-8"
    )

    # 준비 내용 로그 (실행 전 점검용)
    _ev("prepare", "info", f"workspace: {job_root}")
    _ev("prepare", "info", f"compile-db-path: {executor.to_exec_path(compile_db_abs)}")
    _ev("prepare", "info", f"out-test-folder: {executor.to_exec_path(out_abs)}")
    _ev("prepare", "info", f"file-list ({len(exec_files)}개):\n" + "\n".join(exec_files))
    _ev("prepare", "info", ".env (key 값 마스킹):\n" + _masked_env_text(env_dict))

    # 6) GENUT 실행 전: 가상환경(.venv) 준비 후 인터프리터를 venv python으로 치환
    run_head = shlex.split(genut.run_command)
    if use_venv:
        venv_python = _prepare_venv(
            executor, genut_dir, timeout=genut_timeout, ev=_ev, stream=on_event is not None
        )
        run_head = _with_venv_python(run_head, venv_python)

    # GENUT CLI argv (run_command + 표준 플래그)
    argv = [
        *run_head,
        "--file-list", executor.to_exec_path(filelist_path),
        "--compile-db-path", executor.to_exec_path(compile_db_abs),
        "--out-test-folder-path", executor.to_exec_path(out_abs),
        "--max-attempts", str(genut.max_attempts),
    ]
    if debug:
        argv.append("--debug")
    if enable_assure:
        argv.append("--enable-assure")
    if job.function_name:
        argv += ["--function-name", job.function_name]

    # 7) 실행 (호스트 또는 컨테이너) — on_event가 있으면 출력을 줄 단위로 스트리밍
    _ev("run", "info", f"$ {' '.join(argv)}")
    on_line = (lambda line: _ev("run", "info", line)) if on_event is not None else None
    proc = executor.run(argv, genut_dir, genut_timeout, on_line=on_line)

    # 8) 결과 수집 (산출물은 호스트 out_abs에 존재; 컨테이너는 bind-mount로 공유)
    generated: list[str] = []
    summary: str | None = None
    success = proc["success"]
    result_path = out_abs / "result.json"
    if result_path.is_file():
        try:
            data = json.loads(result_path.read_text(encoding="utf-8"))
            generated = data.get("generated_files", [])
            counts = data.get("counts", {})
            summary = (
                f"status={data.get('status')} total={counts.get('total')} "
                f"pos={counts.get('positive')} neg={counts.get('negative')}"
            )
            if data.get("status") == "failed":
                success = False
        except (json.JSONDecodeError, OSError):
            pass

    return RunResult(
        success=success,
        returncode=proc["returncode"],
        stdout=proc["stdout"],
        stderr=proc["stderr"],
        result_summary=summary,
        generated_files=generated,
        out_dir=str(out_abs),
    )
