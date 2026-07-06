"""외부 FunctionExtractor 바이너리를 이용한 함수 추출 (없으면 내장 파서 폴백).

clang 기반 C++ 실행파일 `FunctionExtractor`가 우분투 버전별로
`<repo>/tools/func_extractor/{20_04,22_04,24_04}/FunctionExtractor`에 배치된다.
실행 환경이 우분투이고 버전에 맞는 실행파일이 있으면 자체 정규식 파서 대신 이
바이너리로 함수를 추출한다(컴파일 DB를 활용하므로 더 정확하다).

- 실행: `FunctionExtractor <compile_commands.json이 있는 폴더> <대상 파일>`
- 출력: JSON 배열. 항목 예:
  {"name": "aaa", "signature": "aaa(int)", "parameters": [["int"]],
   "code": "void aaa(int a){\n}", "file": "product/bbb.c", "line": 110}

정책(사용자 확정):
- 바이너리가 **없는** 환경(우분투 아님/버전 폴더 없음)에서만 내장 파서를 사용한다.
- 바이너리가 있는데 실행이 실패하면(비정상 종료·타임아웃·JSON 파싱 실패) 폴백하지
  않고 ExtractorError를 던진다 → 준비 job(스캔/변경 감지)이 FAILED로 기록된다.
"""

from __future__ import annotations

import json
import platform
from functools import lru_cache
from pathlib import Path

from genut_service.config import get_settings
from genut_service.paths import normalize_rel_path
from genut_service.runner import subprocess_util
from genut_service.services.c_function_parser import (
    FunctionSpan,
    extract_functions_from_file,
)

_BINARY_NAME = "FunctionExtractor"


class ExtractorError(RuntimeError):
    """FunctionExtractor 실행/출력 파싱 실패 — 바이너리가 있는 환경에서는 job 실패로 이어진다."""


def _repo_root() -> Path:
    # .../genut_service/services/function_extractor.py → parents[2] = repo 루트
    # (tools/는 tests/와 같은 depth, 즉 repo 루트에 있다)
    return Path(__file__).resolve().parents[2]


def _ubuntu_version_folder() -> str | None:
    """우분투면 버전 폴더명('22.04' → '22_04'), 아니면 None."""
    try:
        os_release = platform.freedesktop_os_release()
    except OSError:
        return None  # 비Linux(예: Windows 개발기) 또는 os-release 없음
    if os_release.get("ID") != "ubuntu":
        return None
    version = (os_release.get("VERSION_ID") or "").strip()
    if not version:
        return None
    return version.replace(".", "_")


@lru_cache(maxsize=1)
def find_extractor() -> Path | None:
    """현재 환경에서 사용할 FunctionExtractor 실행파일 경로(없으면 None).

    런타임 중 OS/배치가 바뀌지 않으므로 결과를 캐시한다(테스트는 cache_clear 사용).
    """
    configured = (get_settings().func_extractor_dir or "").strip()
    if not configured:
        return None  # 빈 값 = 비활성
    folder = _ubuntu_version_folder()
    if folder is None:
        return None
    base = Path(configured)
    if not base.is_absolute():
        base = _repo_root() / base
    binary = base / folder / _BINARY_NAME
    return binary if binary.is_file() else None


def describe_extractor() -> str:
    """job 로그용 라벨: 어떤 추출기가 쓰이는지."""
    binary = find_extractor()
    if binary is None:
        return "내장 파서"
    return f"{_BINARY_NAME}({binary.parent.name})"


def _execute(argv: list[str], timeout: int) -> dict:
    """바이너리 실행(테스트에서 이 지점을 monkeypatch한다)."""
    return subprocess_util.run(argv, timeout=timeout)


def _parse_output(stdout: str) -> list[FunctionSpan]:
    """JSON 배열 출력을 FunctionSpan 목록으로 변환한다.

    end_line은 출력에 없으므로 `code`(함수 전문)의 개행 수로 계산한다 —
    diff의 변경 라인 교차 판정에 필요하다.
    """
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ExtractorError(f"{_BINARY_NAME} 출력 JSON 파싱 실패: {exc}") from exc
    if not isinstance(data, list):
        raise ExtractorError(f"{_BINARY_NAME} 출력이 JSON 배열이 아니다: {type(data).__name__}")

    spans: list[FunctionSpan] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name or not isinstance(name, str):
            continue
        try:
            start_line = max(1, int(entry.get("line") or 1))
        except (TypeError, ValueError):
            start_line = 1
        code = entry.get("code")
        newlines = code.count("\n") if isinstance(code, str) else 0
        spans.append(
            FunctionSpan(name=name, start_line=start_line, end_line=start_line + newlines)
        )
    return spans


def extract_functions(root: Path, compile_db_rel: str, file_path: Path) -> list[FunctionSpan]:
    """파일의 함수 정의 목록을 추출한다.

    FunctionExtractor 바이너리가 있으면 그것으로(실패 시 ExtractorError),
    없으면 내장 파서(c_function_parser)로 추출한다(읽기 실패 OSError는 기존대로 전파).
    """
    binary = find_extractor()
    if binary is None:
        return extract_functions_from_file(file_path)

    rel_dir = normalize_rel_path(compile_db_rel) if compile_db_rel else ""
    compile_db_dir = (root / rel_dir) if rel_dir else root
    result = _execute(
        [str(binary), str(compile_db_dir.resolve()), str(Path(file_path).resolve())],
        timeout=get_settings().func_extractor_timeout,
    )
    if not result.get("success"):
        detail = (result.get("stderr") or result.get("stdout") or "").strip()[:500]
        raise ExtractorError(f"{_BINARY_NAME} 실행 실패(rc={result.get('returncode')}): {detail}")
    return _parse_output(result.get("stdout") or "")
