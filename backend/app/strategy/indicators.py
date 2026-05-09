"""기술적 지표 계산 함수.

설계서 03번 5절: 지표 계산과 조건 판단을 분리한다.
이 모듈은 순수 수치 계산만 담당. 신호 발생 / look-ahead bias 방지는
조건 함수의 책임 (예: new_high_breakout이 shift(1)을 적용).

모든 함수는 pandas Series를 입력받아 pandas Series(또는 튜플)를 반환한다.
"""

from __future__ import annotations

import pandas as pd


def moving_average(series: pd.Series, period: int) -> pd.Series:
    """단순 이동평균 (SMA).

    초기 (period - 1)개 구간은 NaN.
    """
    if period < 1:
        raise ValueError(f"period는 1 이상이어야 합니다: {period}")
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """지수 이동평균 (EMA, span 방식).

    `adjust=False`로 표준 EMA 점화식 사용:
        EMA_t = alpha * x_t + (1 - alpha) * EMA_{t-1},  alpha = 2 / (period + 1)
    """
    if period < 1:
        raise ValueError(f"period는 1 이상이어야 합니다: {period}")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI (0~100).

    표준 Wilder 방식: 첫 평균 후 alpha = 1/period 의 EWM smoothing.
    pandas의 `ewm(alpha=1/period, adjust=False, min_periods=period)`로 동등하게 계산.

    - 모든 봉이 상승이면 RSI → 100
    - 모든 봉이 하락이면 RSI → 0
    - 가격 변화 없는 구간은 NaN
    - 최초 valid index는 period (delta가 NaN인 첫 행 + period개 평활화 필요)
    """
    if period < 1:
        raise ValueError(f"period는 1 이상이어야 합니다: {period}")

    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD 라인 / 시그널 라인 / 히스토그램.

    반환: (macd_line, signal_line, histogram)
        macd_line = EMA(close, fast) - EMA(close, slow)
        signal_line = EMA(macd_line, signal)
        histogram = macd_line - signal_line
    """
    if fast < 1 or slow < 1 or signal < 1:
        raise ValueError("fast, slow, signal 모두 1 이상이어야 합니다")
    if fast >= slow:
        raise ValueError(f"fast({fast})는 slow({slow})보다 작아야 합니다")

    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram
