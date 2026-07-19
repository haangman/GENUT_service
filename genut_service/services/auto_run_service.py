"""auto 모드 준비(prep) 작업 코어 (FastAPI/스케줄러 비의존).

- run_scan_job(JJ작업): auto_file_list의 각 파일에 대해 성공/실패 테스트 폴더를 확인,
  테스트가 하나도 없는 파일은 파일 단위 GENUT job, 일부만 있으면 누락 함수별 GENUT job을
  큐잉한다.
- run_diff_job(변경 감지): 코드를 제자리 갱신한 뒤 마지막 스캔 커밋과 HEAD를 diff해,
  auto_file_list 파일의 수정된 함수마다 GENUT job을 큐잉한다. 기준 커밋은 전 과정이
  성공했을 때만 전진한다(실패 시 다음 주기에 같은 구간을 재시도).
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
from genut_service.runner import git_ops
from genut_service.services import (
    compile_db_service,
    function_extractor,
    test_status_service,
)
from genut_service.services.c_function_parser import FunctionSpan

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
    아직 체크아웃이 없으면(최초 사이클) 최초 clone까지 수행한다(git 실패는 GitError
    전파 → 준비 job이 실패로 기록된다).
    """
    if not product.code_path:
        raise AutoRunError(
            "auto 실행에는 code_path(영속 코드 경로)가 필요하다 — 프로덕트에 코드 저장 경로를 지정하라"
        )
    root = workspace.resolve_code_path(product.code_path)
    if root.is_dir():
        return root
    return workspace.ensure_product_checkout(product)


class EnqueueContext:
    """스캔/diff 1회 동안 재사용하는 큐잉 컨텍스트.

    함수 1건을 큐잉할 때마다 compile_commands.json을 재파싱하고 pending job 전건을
    다시 읽으면 누락 함수 K개의 첫 사이클이 O(K²)가 된다. 스캔 시작 시 (1) compile DB와
    (2) queued/running GENUT job의 (파일, 함수) 인덱스를 한 번만 만들어 O(K)로 줄인다.
    """

    def __init__(self, session: Session, product: Product, root: Path) -> None:
        rels, bases = compile_db_service.load_compile_db(root, product.compile_db_rel)
        self._compdb_rels = rels
        self._compdb_bases = bases
        # 파일(정규화 상대경로) → {함수명(None=파일 단위): job id}. 새 큐잉도 여기 반영한다.
        self._pending: dict[str, dict[str | None, int]] = {}
        stmt = select(Job).where(
            Job.product_id == product.id,
            Job.kind == JobKind.GENUT.value,
            Job.status.in_(_PENDING_STATUSES),
        )
        for job in session.scalars(stmt):
            for rel in job.file_list or []:
                self._pending.setdefault(normalize_rel_path(rel), {}).setdefault(
                    job.function_name, job.id
                )

    def in_compile_db(self, rel: str) -> bool:
        """split_inclusion과 동일 규칙: 정규화 상대경로 일치 또는 basename 일치."""
        return rel in self._compdb_rels or Path(rel).name in self._compdb_bases

    def pending_job_id(
        self, rel: str, function_name: str | None, *, any_function: bool = False
    ) -> int | None:
        """이번 요청을 대체할 수 있는 pending job의 id를 찾는다(없으면 None).

        - any_function=True(파일 단위 dedup): 그 파일의 어떤 pending job이든 매치.
        - 함수 단위: 같은 함수의 job, 또는 그 파일의 파일 단위(None) job이 매치한다 —
          파일 단위 job은 모든 함수를 생성하므로 함수 job을 대체한다.
        """
        functions = self._pending.get(rel)
        if not functions:
            return None
        if any_function:
            return next(iter(functions.values()))
        if None in functions:
            return functions[None]
        return functions.get(function_name)

    def note_enqueued(self, rel: str, function_name: str | None, job_id: int) -> None:
        self._pending.setdefault(rel, {}).setdefault(function_name, job_id)


def enqueue_genut_job(
    session: Session,
    product: Product,
    root: Path,
    rel_file: str,
    function_name: str | None,
    emit: EmitFn,
    *,
    phase: str = JobPhase.SCAN.value,
    ctx: EnqueueContext | None = None,
) -> Job | None:
    """origin='auto' GENUT job을 큐잉한다. dedup/컴파일DB 미포함이면 스킵하고 None.

    파일 단위 요청(function_name=None)은 그 파일의 어떤 pending job과도 중복으로 본다.
    여러 건을 큐잉할 때는 ctx(EnqueueContext)를 공유해 재파싱/재조회를 피한다.
    """
    if ctx is None:
        ctx = EnqueueContext(session, product, root)
    rel = normalize_rel_path(rel_file)
    label = f"{rel}::{function_name}" if function_name else rel

    pending_id = ctx.pending_job_id(rel, function_name, any_function=function_name is None)
    if pending_id is not None:
        emit(phase, "info", f"스킵(중복): {label} — 대기/실행 중 job #{pending_id}")
        return None

    if not ctx.in_compile_db(rel):
        emit(phase, "warn", f"스킵(컴파일DB 미포함): {label}")
        return None

    job = Job(
        product_id=product.id,
        kind=JobKind.GENUT.value,
        origin=JobOrigin.AUTO.value,
        function_name=function_name or None,
        # JSON 컬럼 aliasing 방지를 위해 항상 새 리스트로 만든다
        file_list=[rel],
        excluded_files=[],
        status=JobStatus.QUEUED.value,
    )
    session.add(job)
    session.commit()
    ctx.note_enqueued(rel, function_name, job.id)
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
    emit(phase, "info", f"함수 추출기: {function_extractor.describe_extractor()}")
    ctx = EnqueueContext(session, product, root)  # compile DB·pending 인덱스 1회 구성

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
            job_created = enqueue_genut_job(
                session, product, root, rel, None, emit, phase=phase, ctx=ctx
            )
            created += job_created is not None
            skipped += job_created is None
            continue

        src = root / rel
        if not src.is_file():
            emit(phase, "warn", f"소스 없음 — 스킵: {rel}")
            warned += 1
            continue
        try:
            # FunctionExtractor 바이너리가 있으면 그것으로, 없으면 내장 파서로 추출.
            # 바이너리 실행 실패(ExtractorError)는 잡지 않고 전파 → 준비 job FAILED.
            spans = function_extractor.extract_functions(root, product.compile_db_rel, src)
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
            job_created = enqueue_genut_job(
                session, product, root, rel, name, emit, phase=phase, ctx=ctx
            )
            created += job_created is not None
            skipped += job_created is None

    return f"파일 {len(rels)}개 스캔: job {created}개 생성, 스킵 {skipped}건, 경고 {warned}건"


def _overlapping_functions(
    spans: list[FunctionSpan], ranges: list[tuple[int, int]]
) -> list[str]:
    """변경 라인 범위와 겹치는 함수 이름 목록(소스 순서, 중복 제거)."""
    names: list[str] = []
    seen: set[str] = set()
    for span in spans:
        if span.name.lower() in seen:
            continue
        if any(start <= span.end_line and end >= span.start_line for start, end in ranges):
            seen.add(span.name.lower())
            names.append(span.name)
    return names


def run_diff_job(
    session: Session,
    job: Job,
    product: Product,
    emit: EmitFn,
    *,
    git_timeout: int = 300,
    should_cancel: Callable[[], bool] | None = None,
    on_process: Callable[[object], None] | None = None,
) -> str:
    """변경 함수 감지 본체. 결과 요약 문자열을 반환한다.

    코드 제자리 갱신 → 기준 커밋(last_scanned_commit)..HEAD의 diff에서 auto_file_list
    파일의 수정(M)된 함수를 판정해 함수별 GENUT job을 큐잉한다. 신규(A)/삭제(D)/리네임(R)
    파일은 누락 스캔(run_scan_job)에 위임한다. 기준 커밋은 전 과정 성공 후에만 전진한다.
    """
    phase = JobPhase.DIFF.value
    root = require_code_root(product)
    old = product.last_scanned_commit

    # 제자리 갱신: fetch+reset(생성 산출물 폴더는 preserve). fetch 실패는 관용 무시되어
    # 기존 체크아웃을 그대로 쓴다(→ HEAD 불변이면 "변경 없음"). on_process로 긴 git
    # 서브프로세스(fetch/clone)를 강제 종료 레지스트리에 노출한다(취소 즉시 반응).
    preserve = [normalize_rel_path(product.out_tests_rel)] if product.out_tests_rel else []
    git_ops.ensure_checkout(
        product.git_url,
        product.git_ref,
        root,
        timeout=git_timeout,
        preserve=preserve,
        on_start=on_process,
        update_mode=product.git_update_mode,
    )
    new = git_ops.head_commit(root, timeout=git_timeout)  # 실패(GitError)면 job 실패·기준 유지

    if old is None:
        product.last_scanned_commit = new
        session.commit()
        emit(phase, "info", f"최초 실행 — 기준 커밋 기록: {new[:12]}")
        return f"최초 실행 — 기준 커밋 기록: {new[:12]} (변경 감지 없음)"
    if old == new:
        return f"변경 없음 ({new[:12]})"

    try:
        changes = git_ops.changed_files(root, old, new, timeout=git_timeout)
    except git_ops.GitError as exc:
        # 기준 커밋 소실(force-push/gc 등) — HEAD로 재기준하고 정상 종료(영구 실패 루프 방지)
        emit(phase, "warn", f"기준 커밋 {old[:12]} 조회 실패 — HEAD로 재기준: {exc}")
        product.last_scanned_commit = new
        session.commit()
        return f"기준 커밋 재설정: {old[:12]} → {new[:12]}"

    auto_set = {normalize_rel_path(f) for f in (product.auto_file_list or []) if f}
    emit(
        phase,
        "info",
        f"{old[:12]}..{new[:12]}: 변경 파일 {len(changes)}개 (대상 파일 {len(auto_set)}개와 대조)",
    )
    emit(phase, "info", f"함수 추출기: {function_extractor.describe_extractor()}")
    ctx = EnqueueContext(session, product, root)  # compile DB·pending 인덱스 1회 구성

    created = 0
    skipped = 0
    touched = 0
    for status, rel in changes:
        if should_cancel is not None and should_cancel():
            raise AutoRunCanceled()
        rel_norm = normalize_rel_path(rel)
        if rel_norm not in auto_set:
            continue
        touched += 1
        if status.startswith("R"):
            if status == "R100":
                # 순수 리네임: 내용이 같고 테스트는 stem(파일명) 기준으로 매칭되므로
                # 재생성이 필요 없다(경로가 바뀌어도 stem이 같으면 기존 테스트 유효).
                emit(phase, "info", f"{rel_norm}: 순수 리네임 — job 없음")
                continue
            # 수정을 동반한 리네임: 옛 경로와의 라인 대응이 어려우므로 안전하게
            # 파일의 전 함수를 재생성 대상으로 본다(dedup이 중복을 흡수한다).
            try:
                spans = function_extractor.extract_functions(
                    root, product.compile_db_rel, root / rel_norm
                )
            except OSError as exc:
                emit(phase, "warn", f"소스 읽기 실패 — 스킵: {rel_norm} ({exc})")
                continue
            changed_fns = _overlapping_functions(spans, [(1, 1 << 31)])
            emit(
                phase,
                "info",
                f"{rel_norm}: 리네임+수정({status}) — 전 함수 {len(changed_fns)}개 재생성",
            )
            for name in changed_fns:
                job_created = enqueue_genut_job(
                    session, product, root, rel_norm, name, emit, phase=phase, ctx=ctx
                )
                created += job_created is not None
                skipped += job_created is None
            continue
        if status != "M":
            emit(phase, "info", f"{rel_norm}: 변경 유형 {status} — 누락 스캔에 위임")
            continue
        ranges = git_ops.diff_new_line_ranges(root, old, new, rel_norm, timeout=git_timeout)
        try:
            spans = function_extractor.extract_functions(
                root, product.compile_db_rel, root / rel_norm
            )
        except OSError as exc:
            emit(phase, "warn", f"소스 읽기 실패 — 스킵: {rel_norm} ({exc})")
            continue
        changed_fns = _overlapping_functions(spans, ranges)
        if not changed_fns:
            emit(phase, "info", f"{rel_norm}: 함수 영역 밖 변경 — job 없음")
            continue
        emit(phase, "info", f"{rel_norm}: 변경 함수 {len(changed_fns)}개 ({', '.join(changed_fns)})")
        for name in changed_fns:
            job_created = enqueue_genut_job(
                session, product, root, rel_norm, name, emit, phase=phase, ctx=ctx
            )
            created += job_created is not None
            skipped += job_created is None

    product.last_scanned_commit = new  # ★ 전 과정 성공 후에만 전진
    session.commit()
    return (
        f"{old[:12]}..{new[:12]}: 대상 파일 변경 {touched}건, "
        f"job {created}개 생성, 스킵 {skipped}건"
    )
