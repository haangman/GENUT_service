"""GENUT가 읽을 .env를 프로덕트 + GENUT 인스턴스 정보로 조립한다."""

from __future__ import annotations

from pathlib import Path

from genut_service.db.models import GenutInstance, Product


def build_env(product: Product, genut: GenutInstance) -> dict[str, str]:
    """.env 키 매핑: DS_ASSIST_*·LLM_MODEL은 GENUT 인스턴스, 나머지는 프로덕트."""
    return {
        "TEST_GENERATION_MODE": product.test_generation_mode,
        "DS_ASSIST_CREDENTIAL_KEY": genut.ds_assist_credential_key,
        "DS_ASSIST_USER_ID": genut.ds_assist_user_id or "",
        "DS_ASSIST_SEND_SYSTEM_NAME": genut.ds_assist_send_system_name,
        "CMAKE_CONFIGURE_CMD": product.cmake_configure_cmd,
        "CMAKE_BUILD_CMD": product.cmake_build_cmd,
        "TEST_RUN_CMD": product.test_run_cmd,
        # ORM 기본값은 flush 시점에 적용되므로, 미저장 인스턴스도 기본값으로 폴백한다
        "LLM_MODEL": genut.llm_model or "gptOss",
    }


def write_env_file(path: Path, env: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in env.items()]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
