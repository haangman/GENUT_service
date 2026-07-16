"""외부 프로세스 실행 래퍼. 예외 대신 결과 dict을 반환한다."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Callable


def kill_tree(proc: object) -> None:
    """Popen과 그 자식 프로세스 트리를 강제 종료한다(best-effort, 크로스플랫폼).

    run_streaming이 start_new_session=True로 띄우므로 POSIX에서는 프로세스 그룹(setsid)을
    통째로 죽일 수 있고(빌드/컴파일러 등 손자 프로세스 포함), Windows에서는 `taskkill /T`로
    자식 트리까지 정리한다. pid가 없거나 실패하면 부모만 terminate/kill로 폴백한다.
    """
    if proc is None:
        return
    pid = getattr(proc, "pid", None)
    if pid is not None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
                return
            try:
                pgid = os.getpgid(pid)
            except ProcessLookupError:
                # 리더(직계 자식)가 이미 죽어도 setsid로 만든 프로세스 그룹 id는
                # 리더 pid와 같으므로, 남은 손자들을 그룹으로 정리할 수 있다.
                pgid = pid
            os.killpg(pgid, getattr(signal, "SIGKILL", 9))
            return
        except Exception:  # noqa: BLE001 - 이미 죽었거나 권한/플랫폼 문제면 폴백
            pass
    for method in ("terminate", "kill"):
        try:
            getattr(proc, method)()
        except Exception:  # noqa: BLE001
            pass


def run(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict | None = None,
    encoding: str = "utf-8",
) -> dict:
    """argv를 실행하고 {success, returncode, stdout, stderr}를 반환한다.

    타임아웃 시 kill_tree로 **프로세스 트리 전체**를 종료한다 — 부모만 죽이면
    빌드/컴파일러 같은 손자 프로세스가 살아남아 CPU를 소비하고, 락이 해제된 뒤
    같은 체크아웃에 접근하는 다음 job과 경합하기 때문이다.

    encoding: 자식 출력 디코딩. Windows `cmd /c`의 네이티브 출력처럼 콘솔 OEM
    코드페이지(한글 cp949 등)인 경우 호출자가 "oem"을 지정한다(기본 utf-8).
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=encoding,
            errors="replace",
            # 새 세션/프로세스 그룹으로 띄워 kill_tree가 자식까지 통째로 종료할 수 있게 한다
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"success": False, "returncode": None, "stdout": "", "stderr": str(exc)}
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc)
        try:
            # 트리가 죽으면 파이프가 닫혀 곧 반환된다(그동안 모인 출력 수거)
            stdout, _stderr = proc.communicate(timeout=10)
        except Exception:  # noqa: BLE001 - 수거 실패는 무시(이미 실패 처리)
            stdout = ""
        return {
            "success": False,
            "returncode": None,
            "stdout": stdout or "",
            "stderr": f"timeout after {timeout}s",
        }
    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_streaming(
    argv: list[str],
    cwd: str | None = None,
    timeout: int = 600,
    env: dict | None = None,
    on_line: Callable[[str], None] | None = None,
    on_start: Callable[[subprocess.Popen], None] | None = None,
) -> dict:
    """argv를 실행하며 stdout(+stderr)을 줄 단위로 스트리밍한다.

    각 줄이 나올 때마다 on_line(line)을 호출(실시간 로그 기록용)하고, 전체 출력을
    모아 run()과 동일한 형태로 반환한다. stderr는 stdout에 합쳐 시간 순서를 보존한다.
    on_start가 주어지면 프로세스 생성 직후 Popen 핸들로 호출한다(강제 종료 등록용).
    """
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            # 새 세션/프로세스 그룹으로 띄워 kill_tree가 자식까지 통째로 종료할 수 있게 한다.
            # (POSIX: setsid. Windows에서는 무시되며 taskkill /T가 트리를 정리)
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"success": False, "returncode": None, "stdout": "", "stderr": str(exc)}

    if on_start is not None:
        try:
            on_start(proc)
        except Exception:  # noqa: BLE001 - 등록 콜백 실패가 실행을 막지 않도록
            pass

    lines: list[str] = []
    # 반환 이후 잔존 reader의 콜백/누적을 차단한다 — 잔존 reader가 다음 단계와
    # 겹쳐 on_line(→DB 세션 emit)을 계속 호출하면 로그가 섞이고, 스레드 안전하지
    # 않은 세션이 교차 사용되어 job이 영구히 멈출 수 있다.
    stop = threading.Event()

    def _reader() -> None:
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                if stop.is_set():
                    break
                line = raw.rstrip("\n")
                lines.append(line)
                if on_line is not None:
                    try:
                        on_line(line)
                    except Exception:  # noqa: BLE001 - 로그 콜백 실패가 실행을 막지 않도록
                        pass
        except (OSError, ValueError):
            pass  # 파이프가 강제로 닫힌 경우(아래 정리 단계)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    def _finalize_reader() -> None:
        """직계 자식 종료 후에도 reader가 살아 있으면(손자가 파이프 점유) 정리한다.

        예: pip가 rc=0으로 끝났지만 빌드 손자가 stdout을 쥐고 계속 쓰는 경우.
        (1) 콜백을 차단하고, (2) 남은 프로세스 트리를 강제 종료한 뒤, (3) 파이프를
        닫아 손자의 다음 write가 broken pipe로 끝나게 한다. close()가 reader의
        io 락에 걸려 블록될 수 있어 별도 daemon 스레드에서 닫는다.
        """
        reader.join(timeout=5)
        if not reader.is_alive():
            return
        stop.set()
        kill_tree(proc)
        reader.join(timeout=2)
        if reader.is_alive() and proc.stdout is not None:
            stdout = proc.stdout

            def _close_quietly() -> None:
                try:
                    stdout.close()
                except Exception:  # noqa: BLE001
                    pass

            threading.Thread(target=_close_quietly, daemon=True).start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        # 트리 전체 종료 — 부모만 죽이면 손자(빌드/컴파일러)가 살아남아 파이프를 쥐고
        # reader 스레드도 함께 잔존한다.
        kill_tree(proc)
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
        _finalize_reader()
        return {
            "success": False,
            "returncode": None,
            "stdout": "\n".join(lines),
            "stderr": f"timeout after {timeout}s",
        }
    _finalize_reader()
    rc = proc.returncode
    return {"success": rc == 0, "returncode": rc, "stdout": "\n".join(lines), "stderr": ""}
