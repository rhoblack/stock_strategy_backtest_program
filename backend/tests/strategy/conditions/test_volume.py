"""volume_ratio 조건 테스트."""

import pandas as pd
import pytest

from app.core.exceptions import InvalidOperatorError
from app.strategy.conditions.volume import VOLUME_RATIO_META, volume_ratio


def _df_with_volume(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"adj_volume": values})


def test_volume_ratio_above_threshold():
    """rolling 평균은 당일 포함. 평균=(100+100+100+100+500)/5=180, 비율=500/180≈2.78 → >=2.0."""
    df = _df_with_volume([100] * 5 + [500])
    result = volume_ratio(df, {"period": 5, "operator": ">=", "value": 2.0})
    assert result.iloc[5] == True  # noqa: E712


def test_volume_ratio_below_threshold():
    df = _df_with_volume([100] * 5 + [80])
    result = volume_ratio(df, {"period": 5, "operator": ">=", "value": 2.0})
    assert result.iloc[5] == False  # noqa: E712


def test_volume_ratio_default_period_20():
    """period 미지정 시 기본 20. 평균=(100*20+1000)/21? rolling(20)이라 마지막 20개=(100*19+1000)/20=145, 비율=1000/145≈6.9."""
    df = _df_with_volume([100] * 20 + [1000])
    result = volume_ratio(df, {"operator": ">=", "value": 2.0})
    assert result.iloc[20] == True  # noqa: E712


def test_volume_ratio_initial_nan_window():
    """rolling 평균이 안 만들어진 구간은 결과가 False (NaN > x → False)."""
    df = _df_with_volume([100] * 10)
    result = volume_ratio(df, {"period": 5, "operator": ">=", "value": 1.0})
    assert (~result.iloc[:4]).all()


def test_volume_ratio_invalid_operator_raises():
    df = _df_with_volume([100] * 10)
    with pytest.raises(InvalidOperatorError):
        volume_ratio(df, {"period": 5, "operator": "between", "value": 2.0})


def test_volume_ratio_meta_required_fields():
    for key in ("type", "category", "parameters", "allowed_in"):
        assert key in VOLUME_RATIO_META
    assert VOLUME_RATIO_META["category"] == "volume"
    assert VOLUME_RATIO_META["requires_position"] is False
