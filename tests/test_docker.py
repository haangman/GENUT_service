"""M8: 실제 컨테이너 실행 테스트. docker 미사용 환경에서는 자동 skip된다.

기본 실행에서는 `-m "not docker"`로 제외된다(pyproject 설정).
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from genut_service.db.models import GenutInstance, Job, Product
from genut_service.docker.client import DockerExecutor, is_docker_available

pytestmark = pytest.mark.docker

_PRODUCT_FIELDS = (
    "name",
    "product_code",
    "git_url",
    "git_ref",
    "compile_db_rel",
    "out_tests_rel",
    "cmake_configure_cmd",
    "cmake_build_cmd",
    "test_run_cmd",
    "test_generation_mode",
)


@pytest.fixture(autouse=True)
def _require_docker() -> None:
    if not is_docker_available():
        pytest.skip("docker 미사용 환경")


def test_docker_executor_runs_fake(
    db_session: Session, make_virtual_product, fake_genut_repo, tmp_path
) -> None:
    from genut_service.runner import genut_runner

    vp = make_virtual_product("dk", sources={"src/a.cpp": "// @genut-fn: foo\n"})
    product = Product(**{key: vp[key] for key in _PRODUCT_FIELDS})
    genut = GenutInstance(
        name="g-dk",
        repo_url=fake_genut_repo["repo_url"],
        run_command=fake_genut_repo["run_command"],
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
    )
    db_session.add_all([product, genut])
    db_session.flush()
    job = Job(product_id=product.id, genut_instance_id=genut.id, file_list=["src/a.cpp"])
    db_session.add(job)
    db_session.commit()

    result = genut_runner.run(
        job,
        product,
        genut,
        workspace_root=str(tmp_path),
        make_executor=lambda job_root: DockerExecutor("python:3.12-slim", job_root),
    )
    assert result.success
    assert result.generated_files
