"""파일트리/compile-check 스키마."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TreeEntry(BaseModel):
    name: str
    path: str
    type: Literal["file", "dir"]


class TreeResponse(BaseModel):
    entries: list[TreeEntry]


class CompileCheckRequest(BaseModel):
    files: list[str]


class CompileCheckResponse(BaseModel):
    included: list[str]
    excluded: list[str]
