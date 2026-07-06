"""FunctionExtractor(외부 바이너리) 통합 단위 테스트.

개발기(Windows)에는 바이너리가 없으므로 우분투 감지·실행은 monkeypatch로 모사한다.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from genut_service.config import get_settings
from genut_service.services import function_extractor
from genut_service.services.c_function_parser import FunctionSpan


@pytest.fixture(autouse=True)
def _clear_extractor_cache():
    function_extractor.find_extractor.cache_clear()
    yield
    function_extractor.find_extractor.cache_clear()


def _fake_os_release(id_value: str = "ubuntu", version: str = "22.04"):
    def fake() -> dict:
        return {"ID": id_value, "VERSION_ID": version}

    return fake


def _install_binary(base: Path, folder: str = "22_04") -> Path:
    binary = base / folder / "FunctionExtractor"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"fake-elf")
    return binary


# ---------------------------------------------------------------------------
# find_extractor / describe_extractor
# ---------------------------------------------------------------------------


def test_find_extractor_matches_ubuntu_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(platform, "freedesktop_os_release", _fake_os_release(), raising=False)
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tmp_path))
    binary = _install_binary(tmp_path, "22_04")

    assert function_extractor.find_extractor() == binary
    assert function_extractor.describe_extractor() == "FunctionExtractor(22_04)"


def test_find_extractor_none_when_version_folder_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        platform, "freedesktop_os_release", _fake_os_release(version="24.04"), raising=False
    )
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tmp_path))
    _install_binary(tmp_path, "22_04")  # 24_04 폴더는 없음

    assert function_extractor.find_extractor() is None
    assert function_extractor.describe_extractor() == "내장 파서"


def test_find_extractor_none_on_non_ubuntu(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        platform, "freedesktop_os_release", _fake_os_release(id_value="debian"), raising=False
    )
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tmp_path))
    _install_binary(tmp_path, "22_04")

    assert function_extractor.find_extractor() is None


def test_find_extractor_none_when_os_release_unavailable(tmp_path: Path, monkeypatch) -> None:
    # 비Linux(예: Windows 개발기)에서는 freedesktop_os_release가 OSError를 던진다
    def raising() -> dict:
        raise OSError("no os-release")

    monkeypatch.setattr(platform, "freedesktop_os_release", raising, raising=False)
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tmp_path))
    _install_binary(tmp_path, "22_04")

    assert function_extractor.find_extractor() is None


def test_find_extractor_disabled_by_empty_setting(monkeypatch) -> None:
    monkeypatch.setattr(platform, "freedesktop_os_release", _fake_os_release(), raising=False)
    monkeypatch.setattr(get_settings(), "func_extractor_dir", "")

    assert function_extractor.find_extractor() is None


# ---------------------------------------------------------------------------
# 출력 파싱/매핑
# ---------------------------------------------------------------------------


def _enable_fake_binary(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(platform, "freedesktop_os_release", _fake_os_release(), raising=False)
    monkeypatch.setattr(get_settings(), "func_extractor_dir", str(tmp_path))
    return _install_binary(tmp_path)


def test_extract_maps_json_array_to_spans(tmp_path: Path, monkeypatch) -> None:
    _enable_fake_binary(tmp_path, monkeypatch)
    output = json.dumps(
        [
            {
                "name": "aaa",
                "signature": "aaa(int)",
                "parameters": [["int"]],
                "code": "void aaa(int a){\n}",
                "file": "product/bbb.c",
                "line": 110,
            },
            {"name": "ccc", "code": "int ccc(){\n  return 1;\n}", "line": 200},
            {"signature": "이름 없음 — 스킵"},
            "dict가 아닌 항목 — 스킵",
        ]
    )
    executed: list[list[str]] = []

    def fake_execute(argv: list[str], timeout: int) -> dict:
        executed.append(argv)
        return {"success": True, "returncode": 0, "stdout": output, "stderr": ""}

    monkeypatch.setattr(function_extractor, "_execute", fake_execute)

    spans = function_extractor.extract_functions(tmp_path, "build", tmp_path / "src" / "bbb.c")

    # end_line = line + code의 개행 수 (diff 라인 교차 판정용)
    assert spans == [
        FunctionSpan(name="aaa", start_line=110, end_line=111),
        FunctionSpan(name="ccc", start_line=200, end_line=202),
    ]
    # 인자: <compile_commands.json 폴더> <대상 파일> (절대경로)
    argv = executed[0]
    assert argv[0].endswith("FunctionExtractor")
    assert Path(argv[1]) == (tmp_path / "build").resolve()
    assert Path(argv[2]) == (tmp_path / "src" / "bbb.c").resolve()


def test_extract_empty_array_returns_empty(tmp_path: Path, monkeypatch) -> None:
    _enable_fake_binary(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {"success": True, "returncode": 0, "stdout": "[]", "stderr": ""},
    )
    assert function_extractor.extract_functions(tmp_path, "build", tmp_path / "a.c") == []


# ---------------------------------------------------------------------------
# 실패 → ExtractorError (바이너리가 있는 환경에서는 폴백하지 않는다)
# ---------------------------------------------------------------------------


def test_extract_nonzero_exit_raises(tmp_path: Path, monkeypatch) -> None:
    _enable_fake_binary(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {
            "success": False,
            "returncode": 2,
            "stdout": "",
            "stderr": "clang crashed",
        },
    )
    with pytest.raises(function_extractor.ExtractorError, match="clang crashed"):
        function_extractor.extract_functions(tmp_path, "build", tmp_path / "a.c")


def test_extract_invalid_json_raises(tmp_path: Path, monkeypatch) -> None:
    _enable_fake_binary(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {
            "success": True,
            "returncode": 0,
            "stdout": "not-json",
            "stderr": "",
        },
    )
    with pytest.raises(function_extractor.ExtractorError, match="JSON 파싱 실패"):
        function_extractor.extract_functions(tmp_path, "build", tmp_path / "a.c")


def test_extract_non_array_json_raises(tmp_path: Path, monkeypatch) -> None:
    _enable_fake_binary(tmp_path, monkeypatch)
    monkeypatch.setattr(
        function_extractor,
        "_execute",
        lambda argv, timeout: {
            "success": True,
            "returncode": 0,
            "stdout": '{"name": "aaa"}',
            "stderr": "",
        },
    )
    with pytest.raises(function_extractor.ExtractorError, match="배열이 아니다"):
        function_extractor.extract_functions(tmp_path, "build", tmp_path / "a.c")


# ---------------------------------------------------------------------------
# 바이너리 부재 → 내장 파서 폴백
# ---------------------------------------------------------------------------


def test_extract_falls_back_to_builtin_parser_without_binary(
    tmp_path: Path, monkeypatch
) -> None:
    # 우분투가 아니면(개발기 등) 기존 내장 파서로 동작한다
    def raising() -> dict:
        raise OSError("no os-release")

    monkeypatch.setattr(platform, "freedesktop_os_release", raising, raising=False)
    src = tmp_path / "aaa.c"
    src.write_text("int bbb(void) { return 1; }\n", encoding="utf-8")

    spans = function_extractor.extract_functions(tmp_path, "build", src)
    assert [s.name for s in spans] == ["bbb"]
