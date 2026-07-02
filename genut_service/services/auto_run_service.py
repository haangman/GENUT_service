"""auto 모드 준비(prep) 작업 코어 (FastAPI/스케줄러 비의존).

- run_scan_job(JJ작업): auto_file_list의 각 파일에 대해 성공/실패 테스트 폴더를 확인,
  테스트가 하나도 없는 파일은 파일 단위 GENUT job, 일부만 있으면 누락 함수별 GENUT job을
  큐잉한다.
- enqueue_genut_job: dedup(동일 파일/함수의 queued/running job이 있으면 스킵)과
  compile_commands 포함 검사를 거쳐 origin='auto' GENUT job을 만든다.

진행 로그는 emit(phase, level, message) 콜백으로 내보낸다(스케줄러 글루가 JobEvent +
job.log에 기록 — runner/worker.py의 emit과 같은 계약).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Job, Product
from genut_service.enums import JobKind, JobOrigin, JobPhase, JobStatus
from genut_service.paths import normalize_rel_path
from genut_service.services import compile_db_service, test_status_service
from genut_service.services.c_function_parser import extract_functions_from_file

# (phase, level, message) — runner/worker.py의 emit과 동일 계약
EmitFn = Callable[[str, str, str], None]


class AutoRunError(RuntimeError):
    """auto 준비 작업을 실행할 수 없는 상태(예: code_path 미지정)."""


class AutoRunCanceled(Exception):
    """사용자 취소 요청으로 준비 작업을 중단했다."""


# dedup 대상: 아직 결과가 나오지 않은(대기/실행 중) GENUT job
_PENDING_STATUSES = (JobStatus.QUEUED.value, JobStatus.RUNNING.value)


def require_code_root(product: Product) -> Path:
    """auto 실행의 전제인 영속 코드 경로를 반환한다. 불가하면 AutoRunError.

    code_path가 없으면 생성 테스트가 영속적으로 남을 곳이 없어 스캔이 의미가 없다.
    """
    if not product.code_path:
        raise AutoRunError(
            "auto 실행에는 code_path(영속 코드 경로)가 필요하다 — 프로덕트에 코드 저장 경로를 지정하라"
        )
    root = workspace.resolve_code_path(product.code_path)
    if not root.is_dir():
        raise AutoRunError(f"code_path 경로가 존재하지 않는다: {root}")
    return root


def find_pending_genut_job(
    session: Session,
    product_id: int,
    rel_file: str,
    function_name: str | None = None,
    *,
    any_function: bool = False,
) -> Job | None:
    """이번 요청을 대체할 수 있는 queued/running GENUT job을 찾는다(없으면 None).

    - any_function=True(파일 단위 dedup): 그 파일을 포함한 어떤 pending job이든 매치.
    - 함수 단위: 같은 함수의 job, 또는 그 파일의 파일 단위(function_name 없음) job이
      매치한다 — 파일 단위 job은 모든 함수를 생성하므로 함수 job을 대체한다.

    file_list는 JSON 컬럼이라 파이썬에서 비교한다(pending job 수는 작다).
    """
    stmt = select(Job).where(
        Job.product_id == product_id,
        Job.kind == JobKind.GENUT.value,
        Job.status.in_(_PENDING_STATUSES),
    )
    for job in session.scalars(stmt):
        if rel_file not in (job.file_list or []):
            continue
        if any_function:
            return job
        if job.function_name is None or job.function_name == function_name:
            return job
    return None


def enqueue_genut_job(
    session: Session,
    product: Product,
    root: Path,
    rel_file: str,
    function_name: str | None,
    emit: EmitFn,
    *,
    phase: str = JobPhase.SCAN.value,
) -> Job | None:
    """origin='auto' GENUT job을 큐잉한다. dedup/컴파일DB 미포함이면 스킵하고 None.

    파일 단위 요청(function_name=None)은 그 파일의 어떤 pending job과도 중복으로 본다.
    """
    rel = normalize_rel_path(rel_file)
    label = f"{rel}::{function_name}" if function_name else rel

    pending = find_pending_genut_job(
        session, product.id, rel, function_name, any_function=function_name is None
    )
    if pending is not None:
        emit(phase, "info", f"스킵(중복): {label} — 대기/실행 중 job #{pending.id}")
        return None

    included, _ = compile_db_service.split_inclusion(root, product.compile_db_rel, [rel])
    if not included:
        emit(phase, "warn", f"스킵(컴파일DB 미포함): {label}")
        return None

    job = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.AUTO.value,
        function_name=function_name or None,
        # JSON 컬럼 aliasing 방지를 위해 항상 새 리스트로 만든다
        file_list=list(included),
        excluded_files=[],
        status=JobStatus.QUEUED.value,
    )
    session.add(job)
    session.commit()
    kind_label = f"함수 {function_name}" if function_name else "파일 전체"
    emit(phase, "info", f"job #{job.id} 큐잉: {rel} ({kind_label})")
    return job


def _covered_functions(test_files: list[str]) -> set[str]:
    """테스트 파일 목록에서 커버된 함수명(소문자) 집합을 만든다.

    `<함수명>_Test.<ext>`/`<함수명>_test.<ext>`(대소문자 무시)만 함수로 역산한다.
    """
    covered: set[str] = set()
    for rel in test_files:
        stem = Path(rel).name.rsplit(".", 1)[0]
        if stem.lower().endswith("_test"):
            name = stem[: -len("_test")]
            if name:
                covered.add(name.lower())
    return covered


def run_scan_job(
    session: Session,
    job: Job,
    product: Product,
    emit: EmitFn,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> str:
    """누락 테스트 스캔(JJ작업) 본체. 결과 요약 문자열을 반환한다.

    파일별 규칙:
    - 성공/실패 폴더에 테스트 파일이 하나도 없으면 → 파일 단위 job 1개.
    - 있으면 → 소스의 함수 중 양쪽 폴더 모두에 `<함수>_Test.*`/`<함수>_test.*`가
      없는 함수마다 함수 단위 job.
    """
    phase = JobPhase.SCAN.value
    root = require_code_root(product)
    rels = [normalize_rel_path(f) for f in (product.auto_file_list or []) if f]
    if not rels:
        emit(phase, "info", "대상 파일이 없다 (auto_file_list 비어 있음)")
        return "대상 0개 — 생성할 job 없음"

    success, failed = test_status_service.scan_generated_tests(root, product)
    emit(
        phase,
        "info",
        f"스캔 시작: 대상 {len(rels)}개, 성공 폴더 stem {len(success)}개, "
        f"실패 폴더 stem {len(failed)}개",
    )

    created = 0
    skipped = 0
    warned = 0
    for rel in rels:
        if should_cancel is not None and should_cancel():
            raise AutoRunCanceled()
        stem = Path(rel).name.rsplit(".", 1)[0]
        existing = success.get(stem, []) + failed.get(stem, [])

        if not existing:
            # 성공/실패 어느 쪽에도 테스트가 없다 → 파일 단위 생성
            job_created = enqueue_genut_job(session, product, root, rel, None, emit, phase=phase)
            created += job_created is not None
            skipped += job_created is None
            continue

        src = root / rel
        if not src.is_file():
            emit(phase, "warn", f"소스 없음 — 스킵: {rel}")
            warned += 1
            continue
        try:
            spans = extract_functions_from_file(src)
        except OSError as exc:
            emit(phase, "warn", f"소스 읽기 실패 — 스킵: {rel} ({exc})")
            warned += 1
            continue
        if not spans:
            emit(phase, "warn", f"함수를 찾지 못함 — 스킵: {rel}")
            warned += 1
            continue

        covered = _covered_functions(existing)
        seen: set[str] = set()
        missing: list[str] = []
        for span in spans:
            low = span.name.lower()
            if low in seen:
                continue
            seen.add(low)
            if low not in covered:
                missing.append(span.name)
        emit(
            phase,
            "info",
            f"{rel}: 함수 {len(seen)}개 중 누락 {len(missing)}개 "
            f"(테스트 파일 성공 {len(success.get(stem, []))}·실패 {len(failed.get(stem, []))})",
        )
        for name in missing:
            job_created = enqueue_genut_job(session, product, root, rel, name, emit, phase=phase)
            created += job_created is not None
            skipped += job_created is None

    return f"파일 {len(rels)}개 스캔: job {created}개 생성, 스킵 {skipped}건, 경고 {warned}건"
