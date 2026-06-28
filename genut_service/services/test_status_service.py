"""프로덕트별 테스트 현황 수집 (FastAPI 비의존).

프로덕트의 compile_commands.json에서 **테스트 생성 대상 파일**을 모으고, 프로덕트의
out_tests 폴더를 스캔해 각 대상 파일에 **자동 생성된 테스트 파일**을 매칭한다. 결과는
DB에 저장하지 않고 호출 시점에 체크아웃을 실시간 스캔한다.

매칭 규칙:
- 대상 파일: compile_commands.json의 파일 중 `build`/`Build` 폴더 하위, 폴더명에
  `test`/`Test`가 포함된 경로, 프로덕트별 제외 글롭(`*test*` 등, path 기준 fnmatch)을 제외.
- 테스트 파일: 대상 `aaa.c` → out_tests 하위에서 이름이 `aaa`인 폴더를 찾되, 그 폴더의
  **상위 폴더 이름에 `_fail`이 없을 때만** 그 폴더 직속 파일 중 이름에 `_test`가 포함된
  파일을 생성된 테스트로 본다(대소문자 무시).
"""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

from genut_service.db.models import Product
from genut_service.services import compile_db_service


def _excluded_by_default(rel_path: str) -> bool:
    """build/Build 폴더 하위이거나, 폴더명에 test/Test가 포함되면 제외."""
    segments = rel_path.split("/")
    # 마지막 세그먼트(파일명)는 폴더 규칙에서 제외하고 디렉터리 세그먼트만 본다.
    for seg in segments[:-1]:
        low = seg.lower()
        if low == "build" or "test" in low:
            return True
    return False


def target_files(rels: list[str], exclude_globs: list[str]) -> list[str]:
    """테스트 생성 대상 파일 리스트. 기본 제외(build/test) + 사용자 글롭(path 기준)을 적용."""
    globs = [g for g in (exclude_globs or []) if g.strip()]
    result: list[str] = []
    for rel in rels:
        if _excluded_by_default(rel):
            continue
        if any(fnmatch(rel, glob) for glob in globs):
            continue
        result.append(rel)
    return result


def scan_out_tests(out_root: Path) -> dict[str, list[str]]:
    """out_root 하위를 walk하여 {폴더명: [테스트 파일 상대경로(out_root 기준 POSIX)]} 매핑.

    상위 폴더 이름에 `_fail`이 포함된 폴더는 건너뛴다. 각 폴더 직속 파일 중 이름에
    `_test`가 포함된 파일만 수집한다(대소문자 무시).
    """
    mapping: dict[str, list[str]] = {}
    if not out_root.is_dir():
        return mapping
    out_resolved = out_root.resolve()
    for dirpath, _dirnames, filenames in os.walk(out_resolved):
        current = Path(dirpath)
        # 상위 폴더 이름에 _fail이 있으면 이 폴더(=aaa)의 테스트는 제외
        if "_fail" in current.parent.name.lower():
            continue
        folder_name = current.name
        tests = [
            (current / fn).relative_to(out_resolved).as_posix()
            for fn in sorted(filenames)
            if "_test" in fn.lower()
        ]
        if tests:
            mapping.setdefault(folder_name, []).extend(tests)
    return mapping


def build_status(root: Path, product: Product) -> list[dict]:
    """프로덕트 체크아웃(root)을 스캔해 대상 파일별 테스트 현황을 만든다.

    반환: [{"name", "path", "test_count", "test_files": [{"name","path"}]}] (path 오름차순).
    """
    rels = compile_db_service.list_files(root, product.compile_db_rel)
    targets = target_files(rels, list(product.exclude_globs or []))

    out_rel = (product.out_tests_rel or "").replace("\\", "/").strip("/")
    out_root = (root / out_rel) if out_rel else root
    tests_by_folder = scan_out_tests(out_root)
    # out_root 기준 상대경로를 프로덕트 root 기준으로 환산하기 위한 접두사
    prefix = f"{out_rel}/" if out_rel else ""

    status: list[dict] = []
    for rel in targets:
        stem = Path(rel).name.rsplit(".", 1)[0]
        test_rels = tests_by_folder.get(stem, [])
        test_files = [
            {"name": Path(t).name, "path": f"{prefix}{t}"} for t in test_rels
        ]
        status.append(
            {
                "name": Path(rel).name,
                "path": rel,
                "test_count": len(test_files),
                "test_files": test_files,
            }
        )
    return status


def merge_status(pairs: list[tuple[str, list[dict]]]) -> list[dict]:
    """여러 프로덕트(동명 변이)의 build_status 결과를 path 기준 합집합으로 병합한다.

    입력은 `(product_code, build_status결과)` 쌍 목록. 같은 path의 대상 파일/테스트 파일은
    한 번만 세고(중복 제거), 각 파일에 그것이 등장한 `product_codes`(프로덕트 id)를 붙인다.
    반환: [{"name","path","product_codes","test_count","test_files":[{"name","path","product_codes"}]}]
    (대상 파일 path 오름차순, 각 test_files도 path 오름차순).
    """
    # path -> {name, codes:set, tf: {tf_path: {name, codes:set}}}
    targets: dict[str, dict] = {}
    for code, status in pairs:
        for item in status:
            entry = targets.setdefault(
                item["path"], {"name": item["name"], "codes": set(), "tf": {}}
            )
            entry["codes"].add(code)
            for tf in item["test_files"]:
                tf_entry = entry["tf"].setdefault(
                    tf["path"], {"name": tf["name"], "codes": set()}
                )
                tf_entry["codes"].add(code)

    result: list[dict] = []
    for path in sorted(targets):
        entry = targets[path]
        test_files = [
            {
                "name": entry["tf"][tf_path]["name"],
                "path": tf_path,
                "product_codes": sorted(entry["tf"][tf_path]["codes"]),
            }
            for tf_path in sorted(entry["tf"])
        ]
        result.append(
            {
                "name": entry["name"],
                "path": path,
                "product_codes": sorted(entry["codes"]),
                "test_count": len(test_files),
                "test_files": test_files,
            }
        )
    return result
