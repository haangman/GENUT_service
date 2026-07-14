"""테스트 현황 스냅샷 저장/조회 (FastAPI 비의존).

메인 프로세스의 백그라운드 리프레셔가 (프로젝트, 이름) 그룹별 현황을 미리 계산해
`test_status_snapshots`에 저장하고, API(메인 서버·독립 상태 서버)는 이를 읽어
즉시 응답한다. 쓰기는 리프레셔(단일 writer)만, 읽기는 여러 프로세스가 공유한다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from genut_service.db.models import Product, TestStatusSnapshot
from genut_service.services import test_status_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def group_fingerprint(group: list[Product]) -> str:
    """그룹의 (id, updated_at) 직렬화 — 프로덕트 등록/수정으로 스냅샷이
    오래됐는지 판별하는 지문이다."""
    return "|".join(f"{p.id}:{p.updated_at}" for p in group)


def build_summary(project: str, name: str, group: list[Product], merged: list[dict]) -> dict:
    """merge_status 결과에서 요약(NameTestSummary 형태 dict)을 만든다."""
    return {
        "project": project,
        "name": name,
        "product_codes": [p.product_code for p in group],
        "test_generation_mode": group[0].test_generation_mode,
        "target_file_count": len(merged),
        "total_test_count": sum(row["test_count"] for row in merged),
        "total_case_count": sum(row["case_count"] for row in merged),
        "total_fail_count": sum(row["fail_count"] for row in merged),
    }


def refresh_snapshots(session: Session) -> int:
    """전체 (프로젝트, 이름) 그룹의 스냅샷을 재계산해 저장한다. 저장한 그룹 수를 반환.

    파일시스템 스캔(느릴 수 있음 — clone 포함) 동안 DB 트랜잭션을 잡지 않도록,
    프로덕트를 읽고 detach한 뒤 read 트랜잭션을 닫고 스캔한다. 저장(업서트 +
    사라진 키 삭제)은 마지막에 짧은 트랜잭션 한 번으로 한다.
    """
    products = session.scalars(select(Product).order_by(Product.id)).all()
    groups: dict[tuple[str, str], list[Product]] = {}
    for product in products:
        groups.setdefault((product.project, product.name), []).append(product)
    # detach 후 commit: 이미 로드된 컬럼 값은 유지되고, 스캔 동안 트랜잭션이 없다
    session.expunge_all()
    session.commit()

    results: dict[tuple[str, str], tuple[str, dict, list[dict]]] = {}
    for (project, name), group in groups.items():
        fingerprint = group_fingerprint(group)
        merged = test_status_service.merge_status(test_status_service.scan_group(group))
        results[(project, name)] = (
            fingerprint,
            build_summary(project, name, group, merged),
            merged,
        )

    now = _utcnow()
    for (project, name), (fingerprint, summary, detail) in results.items():
        row = session.get(TestStatusSnapshot, (project, name))
        if row is None:
            session.add(
                TestStatusSnapshot(
                    project=project,
                    name=name,
                    fingerprint=fingerprint,
                    summary=summary,
                    detail=detail,
                    generated_at=now,
                )
            )
        else:
            row.fingerprint = fingerprint
            row.summary = summary
            row.detail = detail
            row.generated_at = now
    # 사라진 (project, name) 키 삭제 — 복합키 NOT IN 대신 이식성 있게 파이썬 차집합.
    # 스냅샷 행 수는 그룹 수 수준이라 개별 delete로 충분히 저렴하다.
    existing = {
        (project, name)
        for project, name in session.execute(
            select(TestStatusSnapshot.project, TestStatusSnapshot.name)
        )
    }
    for project, name in existing - set(results):
        session.execute(
            delete(TestStatusSnapshot).where(
                TestStatusSnapshot.project == project,
                TestStatusSnapshot.name == name,
            )
        )
    session.commit()
    return len(results)


def load_summaries(session: Session, project: str) -> dict[str, tuple[dict, datetime]]:
    """프로젝트의 이름 → (summary dict, generated_at) 맵.
    detail 컬럼은 로드하지 않는다(요약 폴링 경량화)."""
    rows = session.execute(
        select(
            TestStatusSnapshot.name,
            TestStatusSnapshot.summary,
            TestStatusSnapshot.generated_at,
        ).where(TestStatusSnapshot.project == project)
    ).all()
    return {name: (summary, generated_at) for name, summary, generated_at in rows}


def load_detail(session: Session, project: str, name: str) -> list[dict] | None:
    """(프로젝트, 이름)의 detail(TargetFileStatus dict 리스트). 스냅샷이 없으면 None."""
    return session.execute(
        select(TestStatusSnapshot.detail).where(
            TestStatusSnapshot.project == project,
            TestStatusSnapshot.name == name,
        )
    ).scalar_one_or_none()
