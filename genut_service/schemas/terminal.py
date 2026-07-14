"""터미널 API 스키마."""

from __future__ import annotations

from pydantic import BaseModel


class TerminalInfo(BaseModel):
    """터미널 가용성. available=False면 reason에 불가 사유가 담긴다."""

    available: bool
    reason: str = ""
