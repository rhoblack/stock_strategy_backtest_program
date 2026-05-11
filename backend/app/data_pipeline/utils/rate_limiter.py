"""RateLimiter — pykrx 요청 간격 제어 + 차단 감지 자동 일시정지 (14번 §6.4).

설계 결정:

    1. **요청 간 최소 간격 (min_interval_seconds)**
        - 기본 0.5초 (14.6.4 §1 "요청 간격 최소 0.5초 이상")
        - 마지막 요청 완료 후 다음 요청 전에 부족한 시간만큼 sleep
        - monotonic clock 사용 → OS 시각 변경 무관

    2. **연속 실패 카운터 (consecutive_failures)**
        - `record_failure()` 호출 시 카운터 증가
        - `record_success()` 호출 시 카운터 리셋
        - 임계값 초과 시 `wait()` 내부에서 block_sleep 적용 (30분 기본)
        - block_sleep 후 카운터 리셋

    3. **sleep_fn 주입** (테스트 용이성)
        - 실배포: `sleep_fn = time.sleep` (기본)
        - 테스트: `sleep_fn = mock_fn` → 실제 sleep 없이 호출 횟수/인자 검증 가능
        - monotonic_fn: `time.monotonic` (기본), 테스트에서 조작 가능

    4. **결정론**
        - 상태는 mutable (카운터 / 마지막 요청 시각) 이지만 인터페이스는 단순
        - 동일 호출 순서 → 동일 sleep 인자 (monotonic_fn이 동일하면)

14번 정책 매핑:
    - §6.4 KRX 차단 대응 — 본 클래스 자체
    - §6.3 재시도 백오프 — PykrxCollector retry와 **계층 구분**:
        * PykrxCollector retry: 단일 요청 실패 시 1s→5s→30s 지수 백오프 (025)
        * RateLimiter: 요청 *간격* 제어 + 연속 실패 N회 감지 시 30분 일시정지
        * 두 계층은 직교 — RateLimiter는 retry 로직을 대체하지 않음
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """pykrx 요청 간격 제어 + 연속 실패 감지 자동 일시정지.

    Args:
        min_interval_seconds: 요청 간 최소 대기 시간 (기본 0.5초).
        max_consecutive_failures: 연속 실패 허용 횟수 (초과 시 block_sleep 적용).
        block_sleep_seconds: 연속 실패 임계 초과 시 일시정지 시간 (기본 1800초=30분).
        sleep_fn: sleep 함수 — 기본 `time.sleep`, 테스트에서 mock 주입 가능.
        monotonic_fn: 단조 시계 함수 — 기본 `time.monotonic`, 테스트에서 mock 주입 가능.

    사용 예:
        limiter = RateLimiter()
        for symbol in symbols:
            limiter.wait()          # 간격 보장 (blocking)
            try:
                result = fetch(symbol)
                limiter.record_success()
            except Exception:
                limiter.record_failure()
                raise
    """

    min_interval_seconds: float = 0.5
    max_consecutive_failures: int = 5
    block_sleep_seconds: float = 1800.0
    sleep_fn: Callable[[float], None] = field(default_factory=lambda: time.sleep)
    monotonic_fn: Callable[[], float] = field(default_factory=lambda: time.monotonic)

    # 내부 상태
    _last_request_time: float = field(init=False, default=0.0)
    _consecutive_failures: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        # mutable 상태 초기화 (dataclass field default와 충돌 방지)
        self._last_request_time = 0.0
        self._consecutive_failures = 0

    def wait(self) -> None:
        """다음 요청 전 최소 간격을 보장하는 blocking sleep.

        1. 연속 실패 임계 초과 확인 → block_sleep 적용 후 카운터 리셋
        2. 마지막 요청 시각 기준 부족한 시간만큼 sleep
        3. 마지막 요청 시각 갱신

        Note:
            이 메서드는 요청 *전*에 호출해야 한다.
            요청 완료 후에는 record_success() 또는 record_failure()를 호출한다.
        """
        now = self.monotonic_fn()

        # 연속 실패 임계 초과 → 자동 일시정지
        if self._consecutive_failures >= self.max_consecutive_failures:
            self.sleep_fn(self.block_sleep_seconds)
            self._consecutive_failures = 0
            # block_sleep 이후 시각 갱신
            now = self.monotonic_fn()

        # 요청 간격 보장
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval_seconds:
            self.sleep_fn(self.min_interval_seconds - elapsed)

        self._last_request_time = self.monotonic_fn()

    def record_success(self) -> None:
        """요청 성공 — 연속 실패 카운터 리셋."""
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        """요청 실패 — 연속 실패 카운터 증가.

        카운터가 max_consecutive_failures 이상이 되면
        다음 wait() 호출 시 block_sleep이 적용된다.
        """
        self._consecutive_failures += 1

    @property
    def consecutive_failures(self) -> int:
        """현재 연속 실패 횟수 (읽기 전용)."""
        return self._consecutive_failures

    @property
    def last_request_time(self) -> float:
        """마지막 요청 완료 시각 (monotonic, 읽기 전용)."""
        return self._last_request_time


__all__ = ["RateLimiter"]
