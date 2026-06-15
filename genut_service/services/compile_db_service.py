"""compile_commands.json을 읽어 소스 파일 포함 여부를 판정한다."""

from __future__ import annotations

import json
from pathlib import Path

from genut_service.paths import normalize_rel_path


def load_compile_db(root: Path, compile_db_rel: str) -> tuple[set[str], set[str]]:
    """compile_commands.json을 읽어 (root 기준 상대경로 집합, basename 집합)을 반환.

    파일이 없거나 비정상이면 빈 집합. `file`이 절대경로면 그대로, 상대면 `directory`
    기준으로 절대화한 뒤 root 기준 상대경로로 변환한다.
    """
    rel_dir = normalize_rel_path(compile_db_rel) if compile_db_rel else ""
    db_path = (root / rel_dir / "compile_commands.json") if rel_dir else (
        root / "compile_commands.json"
    )

    rels: set[str] = set()
    bases: set[str] = set()
    if not db_path.is_file():
        return rels, bases

    try:
        data = json.loads(db_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return rels, bases

    root_resolved = root.resolve()
    for entry in data:
        file_field = entry.get("file")
        if not file_field:
            continue
        file_path = Path(file_field)
        if not file_path.is_absolute():
            file_path = Path(entry.get("directory", "")) / file_field
        try:
            rels.add(file_path.resolve().relative_to(root_resolved).as_posix())
        except ValueError:
            pass
        bases.add(Path(file_field).name)
    return rels, bases


def split_inclusion(
    root: Path, compile_db_rel: str, files: list[str]
) -> tuple[list[str], list[str]]:
    """선택 파일을 (included, excluded)로 분리한다.

    compile_commands.json에 정규화 상대경로가 있거나(우선) basename이 일치하면 included.
    입력 순서를 보존하고 중복은 제거한다.
    """
    rels, bases = load_compile_db(root, compile_db_rel)
    included: list[str] = []
    excluded: list[str] = []
    seen: set[str] = set()
    for raw in files:
        normalized = normalize_rel_path(raw)
        if normalized in seen:
            continue
        seen.add(normalized)
        if normalized in rels or Path(normalized).name in bases:
            included.append(normalized)
        else:
            excluded.append(normalized)
    return included, excluded
