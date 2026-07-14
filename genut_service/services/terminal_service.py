"""웹 터미널 세션 (FastAPI 비의존, POSIX 전용).

서비스 프로세스와 같은 환경에서 인터랙티브 셸을 PTY로 띄운다 — 서비스가 Docker
컨테이너 안에서 돌면 셸도 그 컨테이너 안에서 열린다. Windows(`pty`/`termios`/`fcntl`
미존재)에서는 사용할 수 없고, `terminal_available()`이 그 사유를 돌려준다.

connection당 TerminalSession 1개(= 셸 프로세스 1개). 서버측 전역 레지스트리는 두지
않는다 — 세션 수명이 WebSocket 연결 수명과 같고, 정리는 close()가 책임진다.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from genut_service.config import get_settings
from genut_service.runner import subprocess_util

# POSIX 전용 모듈 — Windows에서는 import가 실패하므로 방어적으로 처리한다.
try:
    import fcntl
    import pty
    import struct
    import termios

    _PTY_OK = True
except ImportError:  # pragma: no cover - Windows 경로
    _PTY_OK = False


def terminal_available() -> tuple[bool, str]:
    """터미널 사용 가능 여부와 불가 사유를 반환한다.

    (True, "")면 사용 가능. 불가 시 (False, 사유). 프론트가 이 사유를 안내로 띄운다.
    """
    if not get_settings().terminal_enabled:
        return False, "터미널이 비활성화되어 있다 (TERMINAL_ENABLED=false)"
    if os.name == "nt" or not _PTY_OK:
        return False, "터미널은 Linux/WSL·Docker 환경에서만 지원된다"
    return True, ""


def resolve_shell() -> str:
    """사용할 셸 경로를 결정한다: 설정값 → $SHELL → /bin/bash → /bin/sh."""
    configured = get_settings().terminal_shell.strip()
    if configured:
        return configured
    env_shell = os.environ.get("SHELL", "").strip()
    if env_shell:
        return env_shell
    return shutil.which("bash") or "/bin/sh"


class TerminalSession:
    """PTY로 셸 하나를 띄우고 read/write/resize/close를 제공한다(POSIX 전용)."""

    def __init__(self, shell: str | None = None, cwd: str | None = None) -> None:
        if not _PTY_OK:  # pragma: no cover - Windows 경로
            raise RuntimeError("PTY는 이 플랫폼에서 지원되지 않는다")
        self.shell = shell or resolve_shell()
        # openpty로 master/slave를 확보하고 셸의 표준 입출력을 slave에 연결한다.
        # start_new_session=True로 새 세션/프로세스 그룹을 만들어 kill_tree가
        # 셸의 자식(빌드/디버거 등)까지 트리째 정리할 수 있게 한다.
        self.master_fd, slave_fd = pty.openpty()
        env = dict(os.environ, TERM="xterm-256color")
        try:
            self.proc = subprocess.Popen(
                [self.shell],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd,
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            # slave는 자식이 물려받았으므로 부모 쪽 핸들은 닫는다(EOF 감지에 필요).
            os.close(slave_fd)

    def read_once(self, size: int = 65536) -> bytes:
        """PTY에서 한 번 읽는다(블로킹). 빈 bytes면 EOF(셸 종료)."""
        try:
            return os.read(self.master_fd, size)
        except OSError:
            return b""

    def write(self, data: bytes) -> None:
        """PTY로 입력을 쓴다(사용자 키 입력)."""
        try:
            os.write(self.master_fd, data)
        except OSError:
            pass

    def resize(self, cols: int, rows: int) -> None:
        """터미널 창 크기를 셸에 알린다(SIGWINCH 유발)."""
        try:
            packed = struct.pack("HHHH", max(rows, 1), max(cols, 1), 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, packed)
        except OSError:
            pass

    def close(self) -> None:
        """셸 프로세스 트리를 종료하고 master fd를 닫는다(멱등)."""
        subprocess_util.kill_tree(self.proc)
        try:
            os.close(self.master_fd)
        except OSError:
            pass
