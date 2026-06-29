"""프로덕트별 테스트 현황 수집 (FastAPI 비의존).

프로덕트의 compile_commands.json에서 **테스트 생성 대상 파일**을 모으고, 프로덕트의
out_tests 폴더(및 그 형제 폴더)를 스캔해 각 대상 파일에 **생성된 테스트 파일**(성공/실패)과
**생성 로그**를 매칭한다. 결과는 DB에 저장하지 않고 호출 시점에 체크아웃을 실시간 스캔한다.

디스크 구조(등록한 출력 폴더 = out_tests_rel = `AA`):
- 성공: `AA/<stem>/*_test*`            (stem = 대상 파일 `aaa.c`의 확장자 제거 이름 `aaa`)
- 실패: `AA_Fail/<stem>/*_test*`       (AA와 같은 depth의 형제)
- 로그: `AA_debug_log/<stem>/<test>.log` (AA와 같은 depth의 형제, 테스트 파일명 확장자→.log)

매칭 규칙:
- 대상 파일: compile_commands.json의 파일 중 `build`/`Build` 폴더 하위, 폴더명에
  `test`/`Test`가 포함된 경로, 프로덕트별 제외 글롭(`*test*` 등, path 기준 fnmatch)을 제외.
- 테스트 파일(성공/실패): stem 폴더 직속 파일 중 이름에 `_test`가 포함된 파일(대소문자 무시).
"""

from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path

from genut_service.db.models import Product
from genut_service.services import compile_db_service

# 테스트 케이스 선언 매크로(GoogleTest + KUnit). 긴 토큰을 앞에 두어 부분일치를 막고,
# 단어경계 + 뒤따르는 `(`로 EXPECT_EQ·INSTANTIATE_TEST_SUITE_P 등 식별자 내부 TEST를 제외한다.
_CASE_RE = re.compile(
    r"\b(?:TYPED_TEST_P|TYPED_TEST|TEST_F|TEST_P|TEST"
    r"|KUNIT_CASE_PARAM|KUNIT_CASE_ATTR|KUNIT_CASE_SLOW|KUNIT_CASE)\s*\("
)

# (절대경로, mtime_ns, size) -> 케이스 수. 변경 없는 파일은 재읽기/재카운트하지 않는다.
_case_cache: dict[tuple[str, int, int], int] = {}


def _count_test_cases(abs_path: Path) -> int | None:
    """테스트 파일 안의 테스트 케이스 수를 센다(없거나 읽기 실패 시 None).

    단일 패스 정규식으로 GoogleTest/KUnit 케이스 선언 매크로를 카운트하고, 파일의
    (경로, mtime, size)로 캐시한다. 휴리스틱이라 주석/문자열 안의 매크로도 셀 수 있다.
    """
    try:
        st = abs_path.stat()
    except OSError:
        return None
    key = (str(abs_path), st.st_mtime_ns, st.st_size)
    cached = _case_cache.get(key)
    if cached is not None:
        return cached
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    count = len(_CASE_RE.findall(text))
    _case_cache[key] = count
    return count


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


def _find_sibling(parent: Path, name_lower: str) -> Path | None:
    """parent 직속에서 이름이 name_lower와 (대소문자 무시) 일치하는 디렉터리를 찾는다."""
    if not parent.is_dir():
        return None
    for entry in parent.iterdir():
        if entry.is_dir() and entry.name.lower() == name_lower:
            return entry
    return None


def _sibling_roots(out_root: Path) -> tuple[Path | None, Path | None]:
    """out_root와 같은 depth의 `<name>_Fail`·`<name>_debug_log` 폴더를 (대소문자 무시) 찾는다.

    반환: (fail_root, log_root). 없으면 각각 None.
    """
    parent = out_root.parent
    base = out_root.name.lower()
    return (
        _find_sibling(parent, f"{base}_fail"),
        _find_sibling(parent, f"{base}_debug_log"),
    )


def allowed_roots(root: Path, product: Product) -> list[Path]:
    """파일 뷰어가 읽을 수 있는 허용 루트(resolve됨): out_root + 형제 _Fail/_debug_log.

    경로 보안 경계로 사용한다(이 밖의 체크아웃 파일은 읽지 못한다).
    """
    out_rel = (product.out_tests_rel or "").replace("\\", "/").strip("/")
    if not out_rel:
        return [root.resolve()]
    out_root = (root / out_rel).resolve()
    fail_root, log_root = _sibling_roots(out_root)
    return [r for r in (out_root, fail_root, log_root) if r is not None]


def _scan_stem_dir(scan_root: Path | None, product_root: Path) -> dict[str, list[str]]:
    """scan_root 직속 stem 폴더의 `_test` 파일을 {stem: [product_root 기준 POSIX 경로]}로 모은다.

    각 stem 폴더 직속 파일 중 이름에 `_test`가 포함된 파일만 수집한다(대소문자 무시).
    """
    mapping: dict[str, list[str]] = {}
    if scan_root is None or not scan_root.is_dir():
        return mapping
    product_resolved = product_root.resolve()
    for stem_dir in sorted(scan_root.iterdir()):
        if not stem_dir.is_dir():
            continue
        tests = [
            f.resolve().relative_to(product_resolved).as_posix()
            for f in sorted(stem_dir.iterdir())
            if f.is_file() and "_test" in f.name.lower()
        ]
        if tests:
            mapping.setdefault(stem_dir.name, []).extend(tests)
    return mapping


def _scan_log_index(
    log_root: Path | None, product_root: Path
) -> dict[str, dict[str, str]]:
    """로그 폴더를 {stem폴더명(소문자): {로그파일명(소문자): product_root 기준 경로}}로 색인한다.

    폴더명·파일명 대소문자를 무시해 매칭하기 위함이다. 실제 프로젝트에서 테스트 파일과
    로그 파일의 `_Test`/`_test` 대소문자가 다른 경우(예: aaa_Test.cpp ↔ aaa_test.log)에도
    로그를 찾을 수 있다.
    """
    index: dict[str, dict[str, str]] = {}
    if log_root is None or not log_root.is_dir():
        return index
    product_resolved = product_root.resolve()
    for stem_dir in log_root.iterdir():
        if not stem_dir.is_dir():
            continue
        files = {
            f.name.lower(): f.resolve().relative_to(product_resolved).as_posix()
            for f in stem_dir.iterdir()
            if f.is_file()
        }
        if files:
            index[stem_dir.name.lower()] = files
    return index


def _log_path_for(
    log_index: dict[str, dict[str, str]], stem: str, test_filename: str
) -> str | None:
    """테스트 파일에 대응하는 로그 파일 경로(product_root 기준). 없으면 None.

    로그 이름은 테스트 파일의 확장자를 `.log`로 바꾼 것이다(대소문자 무시).
    예: aaa_Test.cpp → aaa_Test.log / aaa_test.log 모두 매칭한다.
    """
    files = log_index.get(stem.lower())
    if not files:
        return None
    wanted = (Path(test_filename).stem + ".log").lower()
    return files.get(wanted)


def _test_file_entry(
    rel_path: str,
    log_index: dict[str, dict[str, str]],
    stem: str,
    case_count: int | None = None,
) -> dict:
    """테스트 파일 1건 dict({name, path, log_path, case_count})를 만든다.

    case_count는 성공 파일에만 채운다(실패 파일은 None — 케이스 집계 대상 아님).
    """
    name = Path(rel_path).name
    return {
        "name": name,
        "path": rel_path,
        "log_path": _log_path_for(log_index, stem, name),
        "case_count": case_count,
    }


def build_status(root: Path, product: Product) -> list[dict]:
    """프로덕트 체크아웃(root)을 스캔해 대상 파일별 테스트 현황을 만든다.

    반환: [{"name","path","test_count","test_files","fail_count","failed_test_files"}]
    (path 오름차순). 각 test_files 항목은 {"name","path","log_path"}.
    """
    rels = compile_db_service.list_files(root, product.compile_db_rel)
    targets = target_files(rels, list(product.exclude_globs or []))

    out_rel = (product.out_tests_rel or "").replace("\\", "/").strip("/")
    out_root = (root / out_rel).resolve() if out_rel else root.resolve()
    fail_root, log_root = _sibling_roots(out_root) if out_rel else (None, None)

    success = _scan_stem_dir(out_root, root)
    failed = _scan_stem_dir(fail_root, root)
    log_index = _scan_log_index(log_root, root)

    status: list[dict] = []
    for rel in targets:
        stem = Path(rel).name.rsplit(".", 1)[0]
        test_files = [
            _test_file_entry(p, log_index, stem, _count_test_cases(root / p))
            for p in success.get(stem, [])
        ]
        failed_test_files = [
            _test_file_entry(p, log_index, stem) for p in failed.get(stem, [])
        ]
        status.append(
            {
                "name": Path(rel).name,
                "path": rel,
                "test_count": len(test_files),
                "test_files": test_files,
                "case_count": sum(tf["case_count"] or 0 for tf in test_files),
                "fail_count": len(failed_test_files),
                "failed_test_files": failed_test_files,
            }
        )
    return status


def _merge_test_file(bucket: dict, tf: dict, code: str) -> None:
    """tf_path 키로 테스트 파일을 병합한다(product_codes 합집합, log_path/case_count 첫 비-None)."""
    entry = bucket.setdefault(
        tf["path"],
        {"name": tf["name"], "codes": set(), "log_path": None, "case_count": None},
    )
    entry["codes"].add(code)
    if entry["log_path"] is None and tf.get("log_path"):
        entry["log_path"] = tf["log_path"]
    if entry["case_count"] is None and tf.get("case_count") is not None:
        entry["case_count"] = tf["case_count"]


def _emit_test_files(bucket: dict) -> list[dict]:
    """병합 버킷을 path 오름차순 [{name,path,product_codes,log_path,case_count}] 리스트로."""
    return [
        {
            "name": bucket[path]["name"],
            "path": path,
            "product_codes": sorted(bucket[path]["codes"]),
            "log_path": bucket[path]["log_path"],
            "case_count": bucket[path]["case_count"],
        }
        for path in sorted(bucket)
    ]


def merge_status(pairs: list[tuple[str, list[dict]]]) -> list[dict]:
    """여러 프로덕트(동명 변이)의 build_status 결과를 path 기준 합집합으로 병합한다.

    입력은 `(product_code, build_status결과)` 쌍 목록. 같은 path의 대상 파일/테스트 파일은
    한 번만 세고(중복 제거), 각 파일에 그것이 등장한 `product_codes`(프로덕트 id)를 붙인다.
    성공(test_files)·실패(failed_test_files)를 각각 병합한다.
    """
    # path -> {name, codes:set, tf: {...}, ftf: {...}}
    targets: dict[str, dict] = {}
    for code, status in pairs:
        for item in status:
            entry = targets.setdefault(
                item["path"],
                {"name": item["name"], "codes": set(), "tf": {}, "ftf": {}},
            )
            entry["codes"].add(code)
            for tf in item["test_files"]:
                _merge_test_file(entry["tf"], tf, code)
            for tf in item.get("failed_test_files", []):
                _merge_test_file(entry["ftf"], tf, code)

    result: list[dict] = []
    for path in sorted(targets):
        entry = targets[path]
        test_files = _emit_test_files(entry["tf"])
        failed_test_files = _emit_test_files(entry["ftf"])
        result.append(
            {
                "name": entry["name"],
                "path": path,
                "product_codes": sorted(entry["codes"]),
                "test_count": len(test_files),
                "test_files": test_files,
                "case_count": sum(tf["case_count"] or 0 for tf in test_files),
                "fail_count": len(failed_test_files),
                "failed_test_files": failed_test_files,
            }
        )
    return result
