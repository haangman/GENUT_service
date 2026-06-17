"""M1: ORM 모델 CRUD, 제약, 관계 테스트."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from genut_service.db.models import (
    GenutInstance,
    Job,
    JobEvent,
    Patch,
    Product,
    ProductLock,
)
from genut_service.enums import JobStatus, WorkerStatus


def _make_product(name: str = "demo") -> Product:
    return Product(
        name=name,
        product_code="P-001",
        git_url="https://example.com/repo.git",
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="cmake -S . -B build",
        cmake_build_cmd="cmake --build build",
        test_run_cmd="ctest --test-dir build",
        test_generation_mode="cpp",
    )


def _make_genut(name: str = "genut-1") -> GenutInstance:
    return GenutInstance(
        name=name,
        repo_url="https://example.com/genut.git",
        ds_assist_credential_key="secret-key",
        ds_assist_send_system_name="sys-A",
    )


def test_create_product_with_ordered_patches(db_session: Session) -> None:
    product = _make_product()
    # 일부러 역순으로 추가하여 order_by 동작을 확인한다
    product.patches.append(Patch(order_index=1, name="second", content="diff-2"))
    product.patches.append(Patch(order_index=0, name="first", content="diff-1"))
    db_session.add(product)
    db_session.commit()
    pid = product.id

    db_session.expire_all()
    loaded = db_session.get(Product, pid)
    assert loaded is not None
    assert [p.order_index for p in loaded.patches] == [0, 1]
    assert [p.name for p in loaded.patches] == ["first", "second"]


def test_product_name_allows_duplicates(db_session: Session) -> None:
    # 이름 중복 허용: 서로 다른 id로 등록된다
    a = _make_product("dup")
    b = _make_product("dup")
    db_session.add_all([a, b])
    db_session.commit()
    assert a.id != b.id
    rows = db_session.scalars(select(Product).where(Product.name == "dup")).all()
    assert len(rows) == 2


def test_genut_instance_defaults(db_session: Session) -> None:
    genut = _make_genut()
    db_session.add(genut)
    db_session.commit()
    db_session.refresh(genut)
    assert genut.max_attempts == 10
    assert genut.run_command == "python -m genut"
    assert genut.enabled is True
    assert genut.worker_status == WorkerStatus.IDLE.value
    assert genut.current_job_id is None


def test_job_defaults_and_events(db_session: Session) -> None:
    product = _make_product()
    db_session.add(product)
    db_session.flush()
    job = Job(product_id=product.id)
    db_session.add(job)
    db_session.flush()
    job.events.append(JobEvent(job_id=job.id, message="queued", phase="schedule"))
    job.events.append(JobEvent(job_id=job.id, message="assigned", phase="schedule"))
    db_session.commit()

    db_session.expire_all()
    loaded = db_session.get(Job, job.id)
    assert loaded is not None
    assert loaded.status == JobStatus.QUEUED.value
    assert loaded.file_list == []
    assert loaded.excluded_files == []
    assert loaded.attempt == 0
    assert [e.message for e in loaded.events] == ["queued", "assigned"]


def test_product_lock_is_exclusive_per_product(db_session: Session) -> None:
    product = _make_product()
    genut_a = _make_genut("genut-a")
    genut_b = _make_genut("genut-b")
    db_session.add_all([product, genut_a, genut_b])
    db_session.flush()
    job1 = Job(product_id=product.id)
    job2 = Job(product_id=product.id)
    db_session.add_all([job1, job2])
    db_session.flush()

    db_session.add(
        ProductLock(product_id=product.id, job_id=job1.id, genut_instance_id=genut_a.id)
    )
    db_session.commit()

    # 같은 프로덕트에 두 번째 락 → PK 충돌
    db_session.add(
        ProductLock(product_id=product.id, job_id=job2.id, genut_instance_id=genut_b.id)
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    locks = db_session.scalars(select(ProductLock)).all()
    assert len(locks) == 1


def test_cascade_delete_product_removes_patches(db_session: Session) -> None:
    product = _make_product()
    product.patches.append(Patch(order_index=0, name="p", content="diff"))
    db_session.add(product)
    db_session.commit()
    assert db_session.scalars(select(Patch)).all()

    db_session.delete(product)
    db_session.commit()
    assert db_session.scalars(select(Patch)).all() == []
