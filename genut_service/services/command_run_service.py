"""프로덕트 폼의 명령 시험 실행 서비스 (FastAPI 비의존).

CMAKE_CONFIGURE_CMD/CMAKE_BUILD_CMD 같은 등록 예정 명령을 code_path(체크아웃)를
작업 디렉터리로 실제 실행해 보고 출력을 돌려준다. 등록된 명령이 GENUT에서 셸로
실행되는 것과 같은 방식(플랫폼 셸 경유)을 쓴다. 명령 자체의 실패(비0 exit)는
예외가 아니라 결과(exit_code/output)로 전달한다.
"""

from __future__ import annotations

import os
import time

from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.runner import subprocess_util
from genut_service.schemas.product import RunCommandRequest, RunCommandResponse
from genut_service.services.code_pull_service import raise_if_code_path_busy


class CodePathMissingError(Exception):
    """code_path 디렉터리가 없어 명령을 실행할 수 없다(먼저 다운로드 필요)."""


def run_command(session: Session, req: RunCommandRequest) -> RunCommandResponse:
    """code_path에서 command를 셸로 실행하고 출력·exit code를 반환한다.

    실행 중 job과의 경합은 raise_if_code_path_busy로 차단한다(CodePathBusyError).
    타임아웃(form_cmd_timeout)이면 kill_tree로 프로세스 트리를 정리하고
    exit_code=-1 + 타임아웃 안내를 output에 담아 반환한다.
    """
    dest = workspace.resolve_code_path(req.code_path)
    if not dest.is_dir():
        raise CodePathMissingError(
            f"코드 저장 경로가 없다: {dest} — 먼저 다운로드로 코드를 받아온다"
        )
    raise_if_code_path_busy(session, dest)

    # 등록 명령은 셸 문자열이므로 플랫폼 셸로 감싼다. subprocess_util.run이
    # 새 세션으로 띄우고 타임아웃 시 트리 전체를 종료한다(빌드 손자 프로세스 포함).
    # Windows cmd의 네이티브 출력은 콘솔 OEM 코드페이지(한글 cp949 등)라 utf-8로
    # 디코딩하면 한글 경로/메시지가 깨진다 — oem 코덱으로 디코딩한다.
    if os.name == "nt":
        argv = ["cmd", "/c", req.command]
        output_encoding = "oem"
    else:
        argv = ["/bin/sh", "-c", req.command]
        output_encoding = "utf-8"

    started = time.monotonic()
    result = subprocess_util.run(
        argv,
        cwd=str(dest),
        timeout=get_settings().form_cmd_timeout,
        encoding=output_encoding,
    )
    duration = time.monotonic() - started

    parts = [part for part in (result["stdout"], result["stderr"]) if part]
    output = "\n".join(part.rstrip("\n") for part in parts)
    exit_code = result["returncode"] if result["returncode"] is not None else -1
    return RunCommandResponse(
        exit_code=exit_code, output=output, duration_seconds=round(duration, 1)
    )
