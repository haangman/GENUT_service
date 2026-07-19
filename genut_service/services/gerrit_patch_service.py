"""Gerrit change 주소/번호로 diff를 가져와 폼 패치 내용으로 돌려주는 서비스 (FastAPI 비의존).

주소에서는 change 번호·패치셋만 파싱하고, diff는 프로덕트의 Git URL로
`git fetch refs/changes/…`를 수행해 얻는다 — clone과 같은 git 인증(ssh/http)을
재사용하므로 Gerrit HTTP 자격증명을 따로 받을 필요가 없다. fetch는 기존 code_path
체크아웃에서 증분으로 수행하며 작업 트리는 건드리지 않는다(객체만 수신).
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from genut_service import workspace
from genut_service.config import get_settings
from genut_service.runner import git_ops
from genut_service.schemas.product import FetchGerritPatchRequest, FetchGerritPatchResponse
from genut_service.services.code_pull_service import raise_if_code_path_busy
from genut_service.services.command_run_service import CodePathMissingError


class GerritChangeInputError(Exception):
    """change 주소/번호를 해석할 수 없다."""


# 허용 입력: 번호만(1234, 1234/5) · 옛 UI(#/c/<num>[/<ps>]) ·
# 새 UI(/c/<project>/+/<num>[/<ps>][/<파일 경로>], 쿼리스트링 허용)
_PLAIN_RE = re.compile(r"^(\d+)(?:/(\d+))?$")
_URL_OLD_RE = re.compile(r"#/c/(\d+)(?:/(\d+))?(?:[/?#]|$)")
_URL_NEW_RE = re.compile(r"/c/.+?/\+/(\d+)(?:/(\d+))?(?:[/?#]|$)")


def parse_change_input(text: str) -> tuple[int, int | None]:
    """입력에서 (change 번호, 패치셋|None)을 파싱한다. 실패 시 GerritChangeInputError."""
    stripped = (text or "").strip()
    if stripped:
        match = (
            _PLAIN_RE.match(stripped)
            or _URL_OLD_RE.search(stripped)
            or _URL_NEW_RE.search(stripped)
        )
        if match:
            patchset = match.group(2)
            return int(match.group(1)), int(patchset) if patchset else None
    raise GerritChangeInputError(
        f"Gerrit change 주소를 해석할 수 없다: {text!r} — 예: https://gerrit…/+/1234, 1234/5"
    )


def change_ref(number: int, patchset: int) -> str:
    """Gerrit change ref: refs/changes/<번호 마지막 두 자리(0패딩)>/<번호>/<패치셋>."""
    return f"refs/changes/{number % 100:02d}/{number}/{patchset}"


def latest_patchset(git_url: str, number: int, timeout: int) -> int:
    """ls-remote로 change의 숫자 패치셋 중 최댓값을 찾는다(meta 등 비숫자 ref 제외)."""
    pattern = f"refs/changes/{number % 100:02d}/{number}/*"
    refs = git_ops.ls_remote_refs(git_url, pattern, timeout=timeout)
    patchsets = [
        int(match.group(1)) for ref in refs if (match := re.search(r"/(\d+)$", ref))
    ]
    if not patchsets:
        raise git_ops.GitError(f"change {number}를 원격에서 찾을 수 없다 (ls-remote {pattern})")
    return max(patchsets)


def fetch_gerrit_patch(
    session: Session, req: FetchGerritPatchRequest
) -> FetchGerritPatchResponse:
    """change의 diff(git show)를 가져와 폼 패치용 name/content로 반환한다.

    체크아웃이 없으면 CodePathMissingError(먼저 다운로드), 같은 경로의 job 실행 중이면
    CodePathBusyError, 파싱 실패는 GerritChangeInputError, git 실패는 GitError.
    """
    dest = workspace.resolve_code_path(req.code_path)
    if not (dest / ".git").is_dir():
        raise CodePathMissingError(
            f"코드 저장 경로가 없다: {dest} — 먼저 다운로드로 코드를 받아온다"
        )
    raise_if_code_path_busy(session, dest)

    number, patchset = parse_change_input(req.change)
    timeout = get_settings().git_timeout
    if patchset is None:
        patchset = latest_patchset(req.git_url, number, timeout=timeout)
    ref = change_ref(number, patchset)
    git_ops.fetch_ref(dest, req.git_url, ref, timeout=timeout)
    return FetchGerritPatchResponse(
        name=f"gerrit-{number}-{patchset}",
        content=git_ops.show_commit(dest, "FETCH_HEAD", timeout=timeout),
        ref=ref,
        subject=git_ops.commit_subject(dest, "FETCH_HEAD", timeout=timeout),
    )
