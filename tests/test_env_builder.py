"""env_builder: .env 키 매핑 단위 테스트."""

from __future__ import annotations

from genut_service.db.models import GenutInstance, Product
from genut_service.runner.env_builder import build_env


def _product() -> Product:
    return Product(
        name="p",
        product_code="P-1",
        git_url="u",
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="cfg",
        cmake_build_cmd="bld",
        test_run_cmd="run",
        test_generation_mode="cpp",
    )


def _genut(user_id: str | None) -> GenutInstance:
    return GenutInstance(
        name="g",
        repo_url="u",
        ds_assist_credential_key="secret",
        ds_assist_send_system_name="sysX",
        ds_assist_user_id=user_id,
    )


def test_build_env_includes_user_id() -> None:
    env = build_env(_product(), _genut("userX"))
    assert env["DS_ASSIST_USER_ID"] == "userX"
    assert env["DS_ASSIST_CREDENTIAL_KEY"] == "secret"
    assert env["DS_ASSIST_SEND_SYSTEM_NAME"] == "sysX"


def test_build_env_user_id_none_becomes_empty() -> None:
    env = build_env(_product(), _genut(None))
    assert env["DS_ASSIST_USER_ID"] == ""


def test_build_env_includes_llm_model_default() -> None:
    # 미저장 인스턴스(ORM 기본값 미적용)도 기본 gptOss로 폴백한다
    env = build_env(_product(), _genut("userX"))
    assert env["LLM_MODEL"] == "gptOss"


def test_build_env_includes_selected_llm_model() -> None:
    genut = _genut("userX")
    genut.llm_model = "SSCR_SE"
    env = build_env(_product(), genut)
    assert env["LLM_MODEL"] == "SSCR_SE"
