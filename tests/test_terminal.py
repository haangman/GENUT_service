"""웹 터미널 API/서비스 테스트.

PTY 실동작(WebSocket) 테스트는 POSIX 전용이라 Windows에서는 skip된다.
가용성 판정·셸 해석·info 엔드포인트는 플랫폼 무관하게 커버한다.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from genut_service.config import get_settings
from genut_service.services import terminal_service

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="PTY는 POSIX 전용")


def test_info_reports_availability(client: TestClient) -> None:
    resp = client.get("/api/terminal/info")
    assert resp.status_code == 200
    body = resp.json()
    if os.name == "nt":
        assert body["available"] is False
        assert body["reason"]  # 불가 사유가 담긴다
    else:
        assert body["available"] is True


def test_info_disabled_by_setting(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "terminal_enabled", False)
    body = client.get("/api/terminal/info").json()
    assert body["available"] is False
    assert "TERMINAL_ENABLED" in body["reason"]


def test_terminal_available_toggles_with_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "terminal_enabled", False)
    available, reason = terminal_service.terminal_available()
    assert available is False
    assert "TERMINAL_ENABLED" in reason


def test_resolve_shell_prefers_configured_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "terminal_shell", "/usr/bin/zsh")
    assert terminal_service.resolve_shell() == "/usr/bin/zsh"


def test_resolve_shell_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "terminal_shell", "")
    monkeypatch.setenv("SHELL", "/bin/fish")
    assert terminal_service.resolve_shell() == "/bin/fish"


def test_ws_reports_reason_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """미지원(비활성)이면 ws는 연결 직후 사유를 보내고 닫는다."""
    monkeypatch.setattr(get_settings(), "terminal_enabled", False)
    with client.websocket_connect("/api/terminal/ws") as ws:
        text = ws.receive_text()
        assert "터미널을 사용할 수 없습니다" in text


@POSIX_ONLY
def test_ws_runs_shell_and_echoes(client: TestClient) -> None:
    """PTY 셸에 명령을 입력하면 출력이 돌아온다(POSIX)."""
    with client.websocket_connect("/api/terminal/ws") as ws:
        ws.send_json({"type": "resize", "cols": 100, "rows": 30})
        ws.send_json({"type": "input", "data": "echo genut_marker\n"})
        collected = b""
        for _ in range(40):
            collected += ws.receive_bytes()
            if b"genut_marker" in collected:
                break
        assert b"genut_marker" in collected


@POSIX_ONLY
def test_terminal_session_write_and_read() -> None:
    """TerminalSession이 셸을 띄우고 입출력한다(POSIX)."""
    session = terminal_service.TerminalSession(shell="/bin/sh")
    try:
        session.resize(80, 24)
        session.write(b"echo hello_session\n")
        collected = b""
        for _ in range(40):
            chunk = session.read_once()
            if not chunk:
                break
            collected += chunk
            if b"hello_session" in collected:
                break
        assert b"hello_session" in collected
    finally:
        session.close()
