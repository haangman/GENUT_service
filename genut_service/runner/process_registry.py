"""실행 중인 job의 서브프로세스 레지스트리 (강제 종료용).

인앱 스케줄러라 API 요청 스레드와 워커 스레드가 같은 프로세스에서 돈다. 워커는 GENUT
서브프로세스를 시작할 때 여기에 등록하고, 강제 종료 API는 job_id로 그 프로세스를 죽인다.
스레드 안전(threading.Lock).
"""

from __future__ import annotations

import threading
from typing import Protocol


class _Killable(Protocol):
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


_lock = threading.Lock()
# job_id -> 현재 실행 중인 서브프로세스(Popen). 단계가 바뀌면 최신 프로세스로 덮어쓴다.
_procs: dict[int, _Killable] = {}
# 강제 종료가 요청된 job_id. 등록 시점에 이미 들어 있으면 즉시 죽인다(레이스 대비).
_canceled: set[int] = set()


def _terminate(proc: _Killable) -> None:
    # 프로세스 트리 전체를 강제 종료한다(자식 빌드/컴파일러/툴 프로세스까지). 예외는 무시.
    from genut_service.runner import subprocess_util

    subprocess_util.kill_tree(proc)


def register(job_id: int, proc: _Killable) -> None:
    """job의 현재 서브프로세스를 등록. 이미 취소 요청된 job이면 즉시 종료한다."""
    kill_now = False
    with _lock:
        _procs[job_id] = proc
        if job_id in _canceled:
            kill_now = True
    if kill_now:
        _terminate(proc)


def unregister(job_id: int) -> None:
    """job 종료 시 등록 해제(취소 플래그도 제거)."""
    with _lock:
        _procs.pop(job_id, None)
        _canceled.discard(job_id)


def is_canceled(job_id: int) -> bool:
    with _lock:
        return job_id in _canceled


def has_process(job_id: int) -> bool:
    """현재 등록된 (살아있다고 가정되는) 서브프로세스가 있는지."""
    with _lock:
        return job_id in _procs

def cancel(job_id: int) -> bool:
    """job을 강제 종료 요청. 실행 중 서브프로세스가 있으면 죽이고 True, 없으면 False.

    이후 등록되는 서브프로세스도 register()에서 즉시 종료된다.
    """
    with _lock:
        _canceled.add(job_id)
        proc = _procs.get(job_id)
    if proc is None:
        return False
    _terminate(proc)
    return True
