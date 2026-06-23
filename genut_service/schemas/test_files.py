"""프로덕트별 테스트 파일 등록/다운로드 스키마."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TestFileEntry(BaseModel):
    """등록된 테스트 파일 1건."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    product_name: str
    rel_path: str


class TestFileAddRequest(BaseModel):
    """등록 탭에서 고른 파일들을 프로덕트(이름)별 리스트에 추가."""

    product_name: str
    rel_paths: list[str]


class TestFileRemoveRequest(BaseModel):
    """등록 리스트에서 파일들을 제거."""

    product_name: str
    rel_paths: list[str]


class TestFileDownloadRequest(BaseModel):
    """선택한 파일들을 zip으로 내려받기.

    product_id는 코드 체크아웃을 해석할 대표 프로덕트 id다(같은 이름은 코드 공유).
    """

    product_id: int
    rel_paths: list[str]
