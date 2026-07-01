"""자동 실행 프로덕트 생성 + CMakeLists 스캐폴딩 (FastAPI 비의존).

자동 실행 프로덕트는 단일 프로덕트로 저장되고(product_code는 `auto` 접두), 저장 시 코드
체크아웃의 테스트 출력 폴더(out_tests_rel, 예: `UnitTest`) 아래에:
- 양식1: `<out>/CMakeLists.txt` — 포함 파일마다 `add_subdirectory(<stem> <stem>_UnitTest)`
- 양식2: `<out>/<stem>/CMakeLists.txt` — 템플릿의 placeholder `filename`을 파일 stem으로 치환
를 생성/갱신한다(없으면 생성, 있으면 갱신).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.db.models import Product
from genut_service.paths import normalize_rel_path
from genut_service.schemas.product import ProductCreate, ProductUpdate
from genut_service.services import product_service

# 사용자가 양식을 비워 두면 쓰는 기본 양식2(gtest). placeholder `filename` → 파일 stem.
DEFAULT_CMAKE_TEMPLATE = """set(MODULE_TEST_NAME filename_UnitTest)

file(GLOB SOURCES
    *.cpp
)

add_executable(${MODULE_TEST_NAME} ${SOURCES})

target_link_libraries(${MODULE_TEST_NAME} PRIVATE UnitTest)
target_link_libraries(${MODULE_TEST_NAME} PRIVATE Json)
target_link_libraries(${MODULE_TEST_NAME} PRIVATE Util)
target_link_libraries(${MODULE_TEST_NAME} PRIVATE Kstub)

if (LCOV_ENABLE STREQUAL True)
    add_custom_command(TARGET ${MODULE_TEST_NAME} POST_BUILD COMMAND find ${PROJECT_BINARY_DIR} -name *.gcda -type f -delete | true)
endif()

gtest_discover_tests(${MODULE_TEST_NAME} EXTRA_ARGS --gtest_output=xml:${CMAKE_CURRENT_BINARY_DIR}/gtest_results.xml)
"""


class AutoProductError(ValueError):
    """자동 실행 프로덕트 입력 오류(예: auto 접두 누락)."""


def _stem(rel: str) -> str:
    """대상 파일 상대경로 → 확장자 제거 파일명(예: src/bb.c → bb)."""
    return Path(rel).name.rsplit(".", 1)[0]


def render_cmake(template: str, stem: str) -> str:
    """양식의 placeholder `filename`을 파일 stem으로 치환한다."""
    return template.replace("filename", stem)


def write_scaffolding(
    root: Path, out_tests_rel: str, files: list[str], template: str
) -> Path:
    """out_tests 폴더 + 파일별 하위 폴더와 CMakeLists.txt(양식1/양식2)를 생성/갱신한다.

    반환: 생성된 base(out_tests) 절대경로.
    """
    base = (root / normalize_rel_path(out_tests_rel)) if out_tests_rel else root
    base.mkdir(parents=True, exist_ok=True)
    stems = [_stem(f) for f in files]

    # 양식1: base/CMakeLists.txt 를 현재 파일목록으로 재생성(idempotent).
    lines = [f"add_subdirectory({stem} {stem}_UnitTest)" for stem in stems]
    (base / "CMakeLists.txt").write_text(
        "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
    )

    # 양식2: base/<stem>/CMakeLists.txt 를 템플릿(없으면 기본)으로 (재)작성.
    tpl = template or DEFAULT_CMAKE_TEMPLATE
    for stem in stems:
        sub = base / stem
        sub.mkdir(parents=True, exist_ok=True)
        (sub / "CMakeLists.txt").write_text(render_cmake(tpl, stem), encoding="utf-8")
    return base


def create_auto_product(session: Session, data: ProductCreate) -> Product:
    """자동 실행 프로덕트를 만들고 CMakeLists 스캐폴딩을 생성한다.

    product_code는 `auto`로 시작해야 한다. 프로덕트 저장 후 체크아웃에 폴더/파일을 만든다.
    """
    if not (data.product_code or "").startswith("auto"):
        raise AutoProductError("자동 실행 프로덕트 ID는 'auto'로 시작해야 한다")
    data = data.model_copy(update={"auto_run": True})
    product = product_service.create_product(session, data)
    _scaffold(product)
    return product


def update_auto_product(
    session: Session, product_id: int, data: ProductCreate
) -> Product | None:
    """자동 실행 프로덕트를 수정하고, 갱신된 정보/파일 목록으로 스캐폴딩을 재생성한다.

    존재하지 않으면 None. product_code는 여전히 `auto`로 시작해야 한다.
    """
    if not (data.product_code or "").startswith("auto"):
        raise AutoProductError("자동 실행 프로덕트 ID는 'auto'로 시작해야 한다")
    payload = data.model_dump(exclude={"patches"})
    payload["auto_run"] = True
    product = product_service.update_product(
        session, product_id, ProductUpdate(**payload, patches=data.patches)
    )
    if product is None:
        return None
    _scaffold(product)
    return product


def _scaffold(product: Product) -> None:
    """프로덕트의 체크아웃에 out_tests 폴더/CMakeLists를 생성·갱신한다."""
    root = workspace.ensure_product_checkout(product)
    write_scaffolding(
        root, product.out_tests_rel, list(product.auto_file_list or []), product.cmake_template or ""
    )
