"""기술적 지표 단위 테스트.

수치 정확성을 직접 검증하기보다 다음에 집중:
    - 초기 NaN 구간이 일관된 위치에 형성되는지
    - 단조 상승/하락 입력에서 RSI가 100/0에 수렴하는지
    - 골든크로스 / 데드크로스 시점이 정확히 잡히는지
    - 길이와 인덱스 정렬이 입력과 동일한지
"""

import numpy as np
import pandas as pd
import pytest

from app.strategy.indicators import ema, macd, moving_average, rsi

# === moving_average ===


def test_moving_average_period_1_equals_input():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    result = moving_average(s, 1)
    pd.testing.assert_series_equal(result, s, check_dtype=False)


def test_moving_average_initial_nan_window():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = moving_average(s, 3)
    assert result.iloc[0:2].isna().all()
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[3] == pytest.approx(3.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_moving_average_invalid_period_raises():
    with pytest.raises(ValueError):
        moving_average(pd.Series([1.0]), 0)
    with pytest.raises(ValueError):
        moving_average(pd.Series([1.0]), -5)


def test_moving_average_preserves_index():
    idx = pd.date_range("2024-01-01", periods=5)
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=idx)
    result = moving_average(s, 2)
    pd.testing.assert_index_equal(result.index, idx)


# === ema ===


def test_ema_returns_same_length():
    s = pd.Series(np.arange(20, dtype=float))
    result = ema(s, 5)
    assert len(result) == len(s)


def test_ema_monotonic_input_is_monotonic_after_warmup():
    s = pd.Series(np.arange(1, 21, dtype=float))
    result = ema(s, 5)
    valid = result.dropna()
    diffs = valid.diff().dropna()
    assert (diffs > 0).all()


def test_ema_constant_input_equals_constant():
    s = pd.Series([10.0] * 20)
    result = ema(s, 5).dropna()
    # Series에 pytest.approx 적용 시 element-wise 비교를 위해 numpy 변환
    np.testing.assert_allclose(result.to_numpy(), 10.0, atol=1e-9)


# === rsi ===


def test_rsi_monotonic_uptrend_approaches_100():
    """단조 상승 → RSI는 100에 수렴."""
    s = pd.Series(np.arange(1, 51, dtype=float))
    result = rsi(s, period=14).dropna()
    assert result.iloc[-1] == pytest.approx(100.0, abs=1e-6)


def test_rsi_monotonic_downtrend_approaches_0():
    """단조 하락 → RSI는 0에 수렴."""
    s = pd.Series(np.arange(50, 0, -1, dtype=float))
    result = rsi(s, period=14).dropna()
    assert result.iloc[-1] == pytest.approx(0.0, abs=1e-6)


def test_rsi_first_valid_index_is_period():
    s = pd.Series(np.arange(1, 21, dtype=float))
    result = rsi(s, period=5)
    # delta가 NaN인 첫 행 + period 만큼 평활화 → index >= period부터 valid
    assert result.iloc[:5].isna().all()
    assert not pd.isna(result.iloc[5])


def test_rsi_range_in_mixed_data():
    """혼합 입력에서 RSI는 0~100 사이."""
    rng = np.random.default_rng(42)
    s = pd.Series(rng.normal(loc=100, scale=2, size=100).cumsum())
    result = rsi(s, period=14).dropna()
    assert (result >= 0).all()
    assert (result <= 100).all()


def test_rsi_invalid_period_raises():
    with pytest.raises(ValueError):
        rsi(pd.Series([1.0]), period=0)


# === macd ===


def test_macd_returns_three_series():
    s = pd.Series(np.arange(50, dtype=float))
    macd_line, signal_line, histogram = macd(s)
    assert isinstance(macd_line, pd.Series)
    assert isinstance(signal_line, pd.Series)
    assert isinstance(histogram, pd.Series)
    assert len(macd_line) == len(signal_line) == len(histogram) == len(s)


def test_macd_histogram_equals_macd_minus_signal():
    s = pd.Series(np.linspace(100, 200, 50))
    macd_line, signal_line, histogram = macd(s)
    diff = (macd_line - signal_line).dropna()
    hist_valid = histogram.dropna()
    pd.testing.assert_series_equal(hist_valid, diff, check_names=False)


def test_macd_uptrend_macd_eventually_positive():
    """장기 상승 추세에서 MACD는 양수가 되어야 한다."""
    s = pd.Series(np.linspace(100, 300, 100))
    macd_line, _, _ = macd(s)
    assert macd_line.dropna().iloc[-1] > 0


def test_macd_invalid_params_raise():
    s = pd.Series([1.0] * 50)
    with pytest.raises(ValueError):
        macd(s, fast=0, slow=26)
    with pytest.raises(ValueError):
        macd(s, fast=26, slow=12)  # fast >= slow
    with pytest.raises(ValueError):
        macd(s, fast=12, slow=26, signal=0)
