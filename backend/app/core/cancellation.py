"""CancellationToken — threading.Event 기반 취소 신호 (10번 §4.4).

BacktestEngine.run()에 cancel_token 파라미터로 주입하면,
날짜 루프 상단에서 is_cancelled()를 체크하고 BacktestCancelledError를 raise한다.

설계:
    - threading.Event 기반이므로 asyncio loop가 없어도 사용 가능.
    - BackgroundTasks(또는 future Celery worker)에서 토큰을 생성하고
      routes_backtests의 cancel 엔드포인트가 set()을 호출한다.
    - run_id → CancellationToken 맵은 이 모듈이 관리한다 (프로세스 내 싱글턴).
    - 다중 프로세스 환경(Celery 등)으로 전환 시 Redis Pub/Sub 등으로 교체해야 한다.
      현재 MVP 범위는 단일 프로세스 (BackgroundTasks) 전용.

에러 코드:
    BACKTEST_NOT_RUNNING (10번 §7.1) — 실행 중이 아닌 run에 cancel 요청 시.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional


class BacktestCancelledError(Exception):
    """cancel_token.is_cancelled()가 True일 때 BacktestEngine이 raise."""

    def __init__(self, run_id: int | None = None):
        msg = f"백테스트가 취소되었습니다 (run_id={run_id})."
        super().__init__(msg)
        self.run_id = run_id


class CancellationToken:
    """threading.Event 래퍼.

    Parameters
    ----------
    run_id
        추적용 run_id. 로그/에러 메시지에 사용.
    """

    def __init__(self, run_id: int | None = None):
        self._event = threading.Event()
        self.run_id = run_id

    def cancel(self) -> None:
        """취소 신호를 설정한다. 이후 is_cancelled()는 True를 반환."""
        self._event.set()

    def is_cancelled(self) -> bool:
        """취소 신호가 설정되어 있으면 True."""
        return self._event.is_set()

    def check_cancelled(self) -> None:
        """취소 신호가 설정되어 있으면 BacktestCancelledError를 raise.

        BacktestEngine의 날짜 루프 상단에서 호출한다.
        """
        if self._event.is_set():
            raise BacktestCancelledError(self.run_id)


# === run_id → CancellationToken 레지스트리 ===
# 프로세스 내 싱글턴. 다중 프로세스 환경으로 전환 시 교체 필요.

_registry_lock = threading.Lock()
_registry: Dict[int, CancellationToken] = {}


def register_token(run_id: int) -> CancellationToken:
    """run_id에 대한 새 CancellationToken을 생성하고 레지스트리에 등록.

    이미 등록된 run_id가 있으면 기존 토큰을 덮어씀 (재실행 시 갱신).
    """
    token = CancellationToken(run_id=run_id)
    with _registry_lock:
        _registry[run_id] = token
    return token


def get_token(run_id: int) -> Optional[CancellationToken]:
    """등록된 CancellationToken을 반환. 없으면 None."""
    with _registry_lock:
        return _registry.get(run_id)


def cancel_run(run_id: int) -> bool:
    """run_id에 대한 CancellationToken에 취소 신호를 설정.

    Returns
    -------
    bool
        True: 토큰이 있고 취소 신호 설정 성공.
        False: 등록된 토큰이 없음 (실행 중인 엔진이 없거나 이미 완료).
    """
    with _registry_lock:
        token = _registry.get(run_id)
    if token is None:
        return False
    token.cancel()
    return True


def unregister_token(run_id: int) -> None:
    """실행 종료 후 레지스트리에서 제거. 메모리 누수 방지."""
    with _registry_lock:
        _registry.pop(run_id, None)
