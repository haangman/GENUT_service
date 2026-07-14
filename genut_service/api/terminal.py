"""웹 터미널 API — 가용성 조회 + PTY WebSocket.

`GET /api/terminal/info`로 사용 가능 여부를 알리고, `WS /api/terminal/ws`가
서비스 프로세스와 같은 환경에서 인터랙티브 셸을 연다. 연결 1개 = 셸 1개.

프로토콜(클라→서버, JSON 텍스트 프레임):
  {"type": "input", "data": "<키 입력>"}
  {"type": "resize", "cols": <int>, "rows": <int>}
서버→클라는 PTY 원시 바이트(멀티바이트 경계 문제를 피해 xterm이 디코딩).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from genut_service.schemas.terminal import TerminalInfo
from genut_service.services import terminal_service

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


@router.get("/info", response_model=TerminalInfo)
def terminal_info() -> TerminalInfo:
    """터미널 사용 가능 여부와 불가 사유(프론트 안내용)."""
    available, reason = terminal_service.terminal_available()
    return TerminalInfo(available=available, reason=reason)


@router.websocket("/ws")
async def terminal_ws(ws: WebSocket) -> None:
    """PTY 셸과 WebSocket을 양방향으로 잇는다.

    미지원 환경이면 accept 후 사유를 보내고 닫는다. 지원 환경이면 셸을 띄우고,
    출력 pump(PTY→ws)와 입력 pump(ws→PTY)를 동시에 돌리다 한쪽이 끝나면 정리한다.
    """
    await ws.accept()
    available, reason = terminal_service.terminal_available()
    if not available:
        await ws.send_text(f"\r\n[터미널을 사용할 수 없습니다] {reason}\r\n")
        await ws.close()
        return

    session = terminal_service.TerminalSession()
    loop = asyncio.get_running_loop()

    async def pump_output() -> None:
        """PTY 출력을 읽어 클라이언트로 보낸다. EOF(셸 종료)면 종료."""
        while True:
            # 블로킹 os.read를 스레드풀에서 — 이벤트 루프를 막지 않는다
            data = await loop.run_in_executor(None, session.read_once)
            if not data:
                break
            await ws.send_bytes(data)

    async def pump_input() -> None:
        """클라이언트 입력/리사이즈를 PTY에 반영한다. 연결이 끊기면 종료."""
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "input":
                session.write(str(msg.get("data", "")).encode("utf-8"))
            elif kind == "resize":
                session.resize(int(msg.get("cols", 80)), int(msg.get("rows", 24)))

    output_task = asyncio.create_task(pump_output())
    input_task = asyncio.create_task(pump_input())
    try:
        # 한쪽(셸 종료 또는 연결 끊김)이 끝나면 세션을 접는다
        await asyncio.wait(
            {output_task, input_task}, return_when=asyncio.FIRST_COMPLETED
        )
    except WebSocketDisconnect:
        pass
    finally:
        for task in (output_task, input_task):
            task.cancel()
        session.close()
        try:
            await ws.close()
        except RuntimeError:
            pass  # 이미 닫힘
