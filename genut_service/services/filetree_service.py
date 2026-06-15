"""프로덕트 체크아웃의 파일트리를 한 레벨씩 탐색한다."""

from __future__ import annotations

from pathlib import Path

from genut_service.paths import normalize_rel_path

# 트리에 노출하지 않을 디렉터리/파일
IGNORED_NAMES = {".git"}


def list_dir(root: Path, rel: str = "") -> list[dict]:
    """root 기준 rel 디렉터리의 직속 항목을 반환한다.

    반환: [{"name", "path"(root 기준 상대, posix), "type": "dir"|"file"}, ...]
    디렉터리 우선, 이름 오름차순 정렬. root 밖이거나 디렉터리가 아니면 FileNotFoundError.
    """
    root_resolved = root.resolve()
    rel_norm = normalize_rel_path(rel) if rel else ""
    target = (root_resolved / rel_norm).resolve() if rel_norm else root_resolved

    if target != root_resolved and root_resolved not in target.parents:
        raise FileNotFoundError(rel)
    if not target.is_dir():
        raise FileNotFoundError(rel)

    entries: list[dict] = []
    for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if child.name in IGNORED_NAMES:
            continue
        entries.append(
            {
                "name": child.name,
                "path": child.relative_to(root_resolved).as_posix(),
                "type": "dir" if child.is_dir() else "file",
            }
        )
    return entries
