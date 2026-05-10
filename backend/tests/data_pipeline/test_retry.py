"""data_pipeline.collectors.retry 테스트 (Phase 11 step 025).

검증 항목 (14번 §6.3):
    1. 정상 호출은 재시도 없이 1회만 실행
    2. RetryableError 발생 시 backoff 시퀀스대로 재시도 (1s → 5s → 30s)
    3. 모든 재시도 소진 후에도 RetryableError이면 최종 raise (=큐 보류 신호)
    4. FatalError 발생 시 즉시 raise (재시도 없음)
    5. 일반 Exception 발생 시 즉시 raise (재시도 없음)
    6. RetryableError.retry_after_seconds가 명시되면 backoff 시퀀스 대신 사용
    7. 다중상속 구체 예외 (RetryableCollectorError / FatalCollectorError) 동작 검증
    8. 데코레이터 형태도 동일 동작
    9. backoff=()이면 재시도 없이 1회만

외부 fetch / time.sleep 실호출 0건 (모든 sleep은 mock).
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest

from app.data_pipeline.collectors.retry import (
    DEFAULT_BACKOFF_SECONDS,
    FatalCollectorError,
    RetryableCollectorError,
    retry_call,
    retry_on_retryable,
)
from app.data_pipeline.exceptions import (
    CollectorError,
    DataPipelineError,
    FatalError,
    RetryableError,
)

# ---------------------------------------------------------------------------
# A) 정책 상수 검증 — 14번 §6.3
# ---------------------------------------------------------------------------


def test_default_backoff_matches_policy_14_6_3() -> None:
    """14번 §6.3: 1초 → 5초 → 30초 → 큐."""
    assert DEFAULT_BACKOFF_SECONDS == (1.0, 5.0, 30.0)


# ---------------------------------------------------------------------------
# B) 정상 흐름
# ---------------------------------------------------------------------------


def test_retry_call_returns_value_on_first_success() -> None:
    fn = MagicMock(return_value="ok")
    sleep_fn = MagicMock()

    result = retry_call(fn, 1, 2, sleep_fn=sleep_fn, x=3)

    assert result == "ok"
    fn.assert_called_once_with(1, 2, x=3)
    sleep_fn.assert_not_called()


# ---------------------------------------------------------------------------
# C) 재시도 흐름 — RetryableError
# ---------------------------------------------------------------------------


def test_retry_call_retries_with_backoff_sequence() -> None:
    """1차 실패 → sleep(1) → 2차 실패 → sleep(5) → 3차 성공."""
    fn = MagicMock(
        side_effect=[
            RetryableError("transient 1"),
            RetryableError("transient 2"),
            "ok",
        ]
    )
    sleep_fn = MagicMock()

    result = retry_call(fn, sleep_fn=sleep_fn)

    assert result == "ok"
    assert fn.call_count == 3
    # backoff 시퀀스의 첫 두 단계만 사용
    assert sleep_fn.call_args_list == [(((1.0,)),), (((5.0,)),)]


def test_retry_call_uses_full_backoff_then_raises() -> None:
    """4번 모두 실패 → 마지막 RetryableError raise (=큐 보류 신호)."""
    fn = MagicMock(
        side_effect=[
            RetryableError("1"),
            RetryableError("2"),
            RetryableError("3"),
            RetryableError("final"),
        ]
    )
    sleep_fn = MagicMock()

    with pytest.raises(RetryableError, match="final"):
        retry_call(fn, sleep_fn=sleep_fn)

    assert fn.call_count == 4  # 1 초기 + 3 재시도
    # sleep은 재시도 직전에만 호출 (1.0, 5.0, 30.0)
    assert sleep_fn.call_args_list == [
        (((1.0,)),),
        (((5.0,)),),
        (((30.0,)),),
    ]


def test_retry_call_uses_retry_after_seconds_override() -> None:
    """RetryableError.retry_after_seconds가 명시되면 backoff 단계 대신 사용."""
    fn = MagicMock(
        side_effect=[
            RetryableError("1", retry_after_seconds=0.7),
            RetryableError("2", retry_after_seconds=2.3),
            "ok",
        ]
    )
    sleep_fn = MagicMock()

    result = retry_call(fn, sleep_fn=sleep_fn)

    assert result == "ok"
    assert sleep_fn.call_args_list == [
        (((0.7,)),),
        (((2.3,)),),
    ]


# ---------------------------------------------------------------------------
# D) Fatal / 일반 Exception — 재시도 없음
# ---------------------------------------------------------------------------


def test_retry_call_does_not_retry_on_fatal_error() -> None:
    fn = MagicMock(side_effect=FatalError("permanent"))
    sleep_fn = MagicMock()

    with pytest.raises(FatalError, match="permanent"):
        retry_call(fn, sleep_fn=sleep_fn)

    fn.assert_called_once()
    sleep_fn.assert_not_called()


def test_retry_call_does_not_retry_on_generic_exception() -> None:
    """RuntimeError 같은 일반 예외는 즉시 전파 (재시도 없음)."""
    fn = MagicMock(side_effect=RuntimeError("unexpected"))
    sleep_fn = MagicMock()

    with pytest.raises(RuntimeError, match="unexpected"):
        retry_call(fn, sleep_fn=sleep_fn)

    fn.assert_called_once()
    sleep_fn.assert_not_called()


# ---------------------------------------------------------------------------
# E) 다중상속 구체 예외 — RetryableCollectorError / FatalCollectorError
# ---------------------------------------------------------------------------


def test_retryable_collector_error_is_collector_and_retryable() -> None:
    err = RetryableCollectorError("rate limit", retry_after_seconds=2.0)
    assert isinstance(err, CollectorError)
    assert isinstance(err, RetryableError)
    assert isinstance(err, DataPipelineError)
    assert err.retry_after_seconds == 2.0


def test_fatal_collector_error_is_collector_and_fatal() -> None:
    err = FatalCollectorError("auth failed")
    assert isinstance(err, CollectorError)
    assert isinstance(err, FatalError)
    assert isinstance(err, DataPipelineError)


def test_retry_call_treats_retryable_collector_error_as_retryable() -> None:
    fn = MagicMock(
        side_effect=[
            RetryableCollectorError("503 from KRX"),
            "ok",
        ]
    )
    sleep_fn = MagicMock()

    assert retry_call(fn, sleep_fn=sleep_fn) == "ok"
    assert fn.call_count == 2
    sleep_fn.assert_called_once_with(1.0)


def test_retry_call_treats_fatal_collector_error_as_fatal() -> None:
    fn = MagicMock(side_effect=FatalCollectorError("schema broken"))
    sleep_fn = MagicMock()

    with pytest.raises(FatalCollectorError):
        retry_call(fn, sleep_fn=sleep_fn)

    fn.assert_called_once()
    sleep_fn.assert_not_called()


# ---------------------------------------------------------------------------
# F) 데코레이터 형태
# ---------------------------------------------------------------------------


def test_retry_on_retryable_decorator_works_like_retry_call() -> None:
    sleep_fn = MagicMock()
    call_count = {"n": 0}

    @retry_on_retryable(backoff=(0.1, 0.2), sleep_fn=sleep_fn)
    def flaky() -> str:
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise RetryableError("once")
        return "ok"

    assert flaky() == "ok"
    assert call_count["n"] == 2
    sleep_fn.assert_called_once_with(0.1)


def test_retry_on_retryable_preserves_function_metadata() -> None:
    @retry_on_retryable()
    def my_function() -> int:
        """docstring."""
        return 1

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "docstring."


# ---------------------------------------------------------------------------
# G) 빈 backoff 시퀀스
# ---------------------------------------------------------------------------


def test_retry_call_with_empty_backoff_no_retry() -> None:
    """backoff=()이면 초기 1회만 호출 — 실패 시 즉시 raise."""
    fn = MagicMock(side_effect=RetryableError("instant"))
    sleep_fn = MagicMock()

    with pytest.raises(RetryableError, match="instant"):
        retry_call(fn, backoff=(), sleep_fn=sleep_fn)

    fn.assert_called_once()
    sleep_fn.assert_not_called()


def test_retry_call_with_empty_backoff_succeeds_on_first() -> None:
    fn = MagicMock(return_value=42)
    sleep_fn = MagicMock()

    assert retry_call(fn, backoff=(), sleep_fn=sleep_fn) == 42
    fn.assert_called_once()


# ---------------------------------------------------------------------------
# H) sleep_fn 시그니처 검증 — Callable[[float], None]
# ---------------------------------------------------------------------------


def test_retry_call_sleep_fn_receives_float_only() -> None:
    received: list[float] = []

    def fake_sleep(seconds: float) -> None:
        received.append(seconds)

    fn = MagicMock(
        side_effect=[
            RetryableError("a"),
            RetryableError("b"),
            "ok",
        ]
    )

    result = retry_call(fn, sleep_fn=fake_sleep)
    assert result == "ok"
    assert received == [1.0, 5.0]
    # 모든 값이 float
    assert all(isinstance(s, float) for s in received)


# ---------------------------------------------------------------------------
# I) 결정론 — 같은 입력 같은 출력 (jitter 없음 확인)
# ---------------------------------------------------------------------------


def test_retry_call_is_deterministic_no_jitter() -> None:
    """동일 시나리오 반복 시 sleep 호출 시퀀스가 항상 같음 (jitter 없음)."""

    def make_run() -> tuple[Callable[..., int], list[float]]:
        sleeps: list[float] = []
        fn = MagicMock(
            side_effect=[
                RetryableError("1"),
                RetryableError("2"),
                42,
            ]
        )
        return fn, sleeps

    runs: list[list[float]] = []
    for _ in range(3):
        fn, sleeps = make_run()
        retry_call(fn, sleep_fn=sleeps.append)
        runs.append(sleeps)

    # 모든 실행에서 sleep 시퀀스가 동일
    assert runs[0] == runs[1] == runs[2] == [1.0, 5.0]
