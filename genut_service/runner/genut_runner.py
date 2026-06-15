"""job 1건을 실행하는 오케스트레이션.

워크스페이스 준비(product clone + patch, GENUT clone) → .env 조립 →
file-list(절대경로) 작성 → 상대→절대 변환 → GENUT CLI 실행 → 결과 수집.
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from genut_service.db.models import GenutInstance, Job, Product
from genut_service.paths import normalize_rel_path
from genut_service.runner import env_builder, git_ops, subprocess_util


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
) -> RunResult:
    job_root = Path(workspace_root) / f"job_{job.id}"
    product_dir = job_root / "product"
    genut_dir = job_root / "genut"
    job_root.mkdir(parents=True, exist_ok=True)

    # 1) 프로덕트 clone + 순서대로 patch 적용 (PatchError/GitError는 호출자가 처리)
    git_ops.clone(product.git_url, product.git_ref, product_dir, timeout=git_timeout)
    for patch in sorted(product.patches, key=lambda p: p.order_index):
        git_ops.apply_patch(str(product_dir), patch.content, timeout=git_timeout)

    # 2) GENUT repo 최신화(clone)
    git_ops.clone(genut.repo_url, genut.repo_ref, genut_dir, timeout=git_timeout)

    # 3) .env 조립 (GENUT 작업 디렉터리에 기록)
    env_builder.write_env_file(genut_dir / ".env", env_builder.build_env(product, genut))

    # 4) 상대→절대 변환
    compile_db_abs = (product_dir / normalize_rel_path(product.compile_db_rel)).resolve()
    out_abs = (product_dir / normalize_rel_path(product.out_tests_rel)).resolve()
    out_abs.mkdir(parents=True, exist_ok=True)

    # 5) file-list (included 절대경로만)
    filelist_path = job_root / "filelist.txt"
    abs_files = [str((product_dir / normalize_rel_path(f)).resolve()) for f in job.file_list]
    filelist_path.write_text(
        "\n".join(abs_files) + ("\n" if abs_files else ""), encoding="utf-8"
    )

    # 6) GENUT CLI argv (run_command + 표준 플래그)
    argv = [
        *shlex.split(genut.run_command),
        "--file-list", str(filelist_path),
        "--compile-db-path", str(compile_db_abs),
        "--out-test-folder-path", str(out_abs),
        "--max-attempts", str(genut.max_attempts),
    ]
    if debug:
        argv.append("--debug")
    if enable_assure:
        argv.append("--enable-assure")
    if job.function_name:
        argv += ["--function-name", job.function_name]

    # 7) 실행
    proc = subprocess_util.run(argv, cwd=str(genut_dir), timeout=genut_timeout)

    # 8) 결과 수집
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
