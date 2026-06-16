"""경로 정규화 유틸. 저장 전 상대경로를 `/` 기준으로 정규화하고 `..`를 거부한다."""

from __future__ import annotations


class PathValidationError(ValueError):
    """허용되지 않는 경로(상위 참조 등)."""


def normalize_rel_path(path: str) -> str:
    """역슬래시→슬래시, 선행 슬래시 제거, `.`/빈 세그먼트 제거, `..` 거부.

    반환값은 프로덕트 루트 기준 상대경로(POSIX 스타일)이다.
    """
    normalized = path.strip().replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for segment in normalized.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            raise PathValidationError(f"상위 경로(..) 참조는 허용되지 않는다: {path!r}")
        parts.append(segment)
    return "/".join(parts)


def normalize_code_path(path: str) -> str:
    """코드 저장 경로 정규화. 절대경로는 그대로, 상대경로는 `..` 거부 후 정규화.

    빈/공백 문자열은 ""을 반환한다(호출부에서 None 처리).
    절대: POSIX 루트(`/...`) 또는 Windows 드라이브(`C:/...`).
    """
    stripped = path.strip().replace("\\", "/")
    if not stripped:
        return ""
    is_absolute = stripped.startswith("/") or (len(stripped) >= 2 and stripped[1] == ":")
    if is_absolute:
        return stripped
    return normalize_rel_path(stripped)
