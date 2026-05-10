"""재시도 / 백오프 정책 (14번 §6.3).

본 모듈은 collector 외부 fetch 호출에 대한 재시도 정책을 제공한다.
14번 §6.3 정책:

```
요청 실패 시:
- 1회: 1초 후 재시도
- 2회: 5초 후 재시도
- 3회: 30초 후 재시도
- 그 이후: 작업 큐에 보류 (본 모듈에서는 마지막 예외를 raise)
```

설계 결정:

    1. **데코레이터 + 함수 양쪽 제공**
        - `@retry_on_retryable()` 데코레이터: PykrxCollector._fetch_* 메서드에 직접 적용
        - `retry_call(fn, *args, **kwargs)` 함수: 동적으로 호출하고 싶을 때

    2. **결정론 (CLAUDE.md #8)**
        - jitter `random.random()` 직접 사용 금지 — 결정론 깨짐
        - 본 step에서는 jitter 없이 고정 backoff `(1.0, 5.0, 30.0)`
        - `RetryableError.retry_after_seconds`가 명시되면 해당 시퀀스의 해당 단계를 override

    3. **Sleep 주입 (테스트 용이성)**
        - `sleep_fn` 매개변수로 `time.sleep`을 교체 가능
        - 테스트는 mock으로 sleep 호출 자체를 카운트만 검증 (실제 대기 0초)

    4. **재시도 대상 / 비대상**
        - 대상: `RetryableError` (그리고 다중상속 `RetryableCollectorError`)
        - 비대상: `FatalError` / `FatalCollectorError` / 기타 Exception → 즉시 raise
        - 14번 §6.3 "연속 실패 5회 알림"은 본 step 범위 밖 (스케줄러/잡 단위 — 028)

    5. **026 이후 재사용**
        - processor / job 단계에서도 retry 정책이 필요해지면 본 모듈을 재사용 가능

본 모듈은 외부 fetch 0건 / 결정론적.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from app.data_pipeline.exceptions import (
    CollectorError,
    FatalError,
    RetryableError,
)

# 14번 §6.3 — 1초 → 5초 → 30초 → 큐(=마지막 예외 raise)
DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 5.0, 30.0)

_P = ParamSpec("_P")
_R = TypeVar("_R")


def retry_call(
    fn: Callable[_P, _R],
    *args: _P.args,
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    **kwargs: _P.kwargs,
) -> _R:
    """`fn(*args, **kwargs)`을 호출하되 RetryableError 발생 시 backoff 시퀀스대로 재시도.

    14번 §6.3 정책 구현:
        - backoff 시퀀스가 `(1.0, 5.0, 30.0)`이면 최대 4회 호출 (초기 1회 + 재시도 3회)
        - 각 재시도 직전 `sleep_fn(backoff[i])` 호출
        - `RetryableError.retry_after_seconds`가 명시되면 해당 시퀀스 단계를 override
        - 모든 재시도 소진 후에도 RetryableError이면 마지막 예외를 raise (=큐 보류 신호)
        - `FatalError` / 기타 Exception은 즉시 raise (재시도 없음)

    Args:
        fn: 호출할 함수.
        *args / **kwargs: 함수 인자.
        backoff: 재시도 간격 시퀀스. 기본 `(1.0, 5.0, 30.0)`.
        sleep_fn: 대기 함수. 테스트에서 mock으로 교체.

    Returns:
        `fn`의 반환값.

    Raises:
        RetryableError: 모든 재시도 후에도 일시 오류.
        FatalError: 즉시 영구 오류.
        Exception: `fn`이 던진 다른 예외 (재시도 없이 즉시 전파).
    """
    last_retryable: RetryableError | None = None
    # 총 시도 횟수 = len(backoff) + 1 (초기 호출 1회 + 재시도 len(backoff)회)
    for attempt in range(len(backoff) + 1):
        try:
            return fn(*args, **kwargs)
        except FatalError:
            # 영구 실패 — 재시도 없이 즉시 전파
            raise
        except RetryableError as exc:
            last_retryable = exc
            if attempt == len(backoff):
                # 마지막 시도였음 — 더 이상 재시도 없이 raise (=큐 보류 신호)
                raise
            # 다음 backoff 단계 결정: retry_after_seconds 우선, 없으면 시퀀스
            wait = (
                exc.retry_after_seconds
                if exc.retry_after_seconds is not None
                else backoff[attempt]
            )
            sleep_fn(wait)
            continue
    # 도달 불가 — for 루프는 반드시 return 또는 raise로 종료된다.
    # 안전망: 만약 backoff가 빈 튜플이면 위 루프가 1회만 도는데 RetryableError가 발생하면 raise됨.
    assert last_retryable is not None  # pragma: no cover
    raise last_retryable  # pragma: no cover


def retry_on_retryable(
    backoff: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """`@retry_on_retryable()` 데코레이터 — `retry_call`의 함수 데코레이터 버전.

    사용 예 (PykrxCollector 내부):

        class PykrxCollector(BaseCollector):
            @retry_on_retryable()
            def _fetch_ohlcv(self, symbol, start, end):
                return pykrx.stock.get_market_ohlcv_by_date(...)

    Args:
        backoff: 재시도 간격 시퀀스. 기본 `(1.0, 5.0, 30.0)`.
        sleep_fn: 대기 함수. 테스트에서 mock으로 교체.

    Returns:
        데코레이터 함수.
    """

    def decorator(fn: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(fn)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            return retry_call(fn, *args, backoff=backoff, sleep_fn=sleep_fn, **kwargs)

        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# 다중상속 구체 예외 (14번 §6.3 / collectors/base.py 인계 §3 / 024 결정)
# ---------------------------------------------------------------------------


class RetryableCollectorError(CollectorError, RetryableError):
    """수집 단계에서 발생한 일시적 오류 — 재시도 대상.

    다중상속 이유 (024 base.py docstring):
        - `CollectorError`: 어느 단계에서 실패했는지(=수집 단계) 분류
        - `RetryableError`: 재시도 정책이 적용되는지 분류
        - 두 분류는 직교이므로 다중상속으로 결합

    호출자는 둘 중 어느 베이스로도 catch 가능:
        - `except CollectorError`: 단계만 관심
        - `except RetryableError`: 재시도만 관심
        - `except RetryableCollectorError`: 정확히 본 케이스만

    Args:
        message: 오류 메시지.
        retry_after_seconds: 권장 재시도 대기 시간 (None이면 기본 backoff 사용).
    """

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        # RetryableError.__init__가 retry_after_seconds를 처리.
        # CollectorError는 message만 받으므로 super() 체인이 RetryableError로 흐름.
        RetryableError.__init__(
            self, message, retry_after_seconds=retry_after_seconds
        )


class FatalCollectorError(CollectorError, FatalError):
    """수집 단계에서 발생한 영구 오류 — 재시도 무의미.

    다중상속 이유: RetryableCollectorError와 동일 (단계 × 재시도 정책 직교).

    예:
        - KRX 인증 실패 (영구)
        - 응답 스키마가 영구적으로 깨진 경우
        - 호출 자체가 잘못된 경우 (잘못된 종목 코드 형식 등)
    """


__all__ = [
    "DEFAULT_BACKOFF_SECONDS",
    "FatalCollectorError",
    "RetryableCollectorError",
    "retry_call",
    "retry_on_retryable",
]
