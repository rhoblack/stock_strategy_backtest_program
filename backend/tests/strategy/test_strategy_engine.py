"""StrategyEngine 단위 테스트.

조건 함수의 정확성은 conditions/test_*.py가 검증.
여기서는 StrategyEngine의 logic 조합과 섹션 라우팅을 검증한다.
"""

import numpy as np
import pandas as pd
import pytest

# 5개 기본 조건이 자동 등록되어 있어야 함
import app.strategy  # noqa: F401
from app.core.exceptions import (
    PositionConditionMisuseError,
    UnknownConditionTypeError,
)
from app.strategy.engine import StrategyEngine


def _df(close: list[float], volume: list[float] | None = None) -> pd.DataFrame:
    n = len(close)
    if volume is None:
        volume = [100.0] * n
    return pd.DataFrame({"adj_close": close, "adj_volume": volume})


# === entry 단일 / 다중 조건 ===


def test_entry_single_condition_passes_through():
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
            ],
        }
    }
    df = _df([100] * 5 + [110])
    result = StrategyEngine(strategy).generate_signals(df)
    assert "entry_signal" in result.columns
    assert "exit_signal" in result.columns
    assert "filter_signal" in result.columns
    assert "final_entry_signal" in result.columns
    assert result["entry_signal"].iloc[5]
    assert result["final_entry_signal"].iloc[5]


def test_entry_and_logic_requires_all_true():
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                {"type": "volume_ratio", "period": 5, "operator": ">=", "value": 2.0},
            ],
        }
    }
    # 가격은 MA 위, 거래량 평균은 100, 마지막은 평균의 2배 미만 → AND 결과 False
    df = _df([100] * 5 + [110], volume=[100] * 5 + [150])
    result = StrategyEngine(strategy).generate_signals(df)
    assert not result["entry_signal"].iloc[5]


def test_entry_or_logic_requires_any_true():
    strategy = {
        "entry": {
            "logic": "OR",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                {"type": "volume_ratio", "period": 5, "operator": ">=", "value": 100.0},
            ],
        }
    }
    df = _df([100] * 5 + [110], volume=[100] * 5 + [150])
    result = StrategyEngine(strategy).generate_signals(df)
    # price_vs_ma는 True, volume_ratio는 False → OR True
    assert result["entry_signal"].iloc[5]


def test_empty_conditions_treated_as_true():
    strategy = {"entry": {"logic": "AND", "conditions": []}}
    df = _df([100, 101, 102])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["entry_signal"].all()


# === filters ===


def test_filters_combined_with_entry_via_and():
    """final_entry_signal = entry & filter."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
        },
        "filters": {
            "logic": "AND",
            "conditions": [{"type": "volume_ratio", "period": 5, "operator": ">=", "value": 100.0}],
        },
    }
    # entry True, filter False → final False
    df = _df([100] * 5 + [110], volume=[100] * 5 + [150])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["entry_signal"].iloc[5]
    assert not result["filter_signal"].iloc[5]
    assert not result["final_entry_signal"].iloc[5]


def test_no_filters_default_filter_signal_true():
    strategy = {
        "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}]}
    }
    df = _df([100, 100, 100, 110])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["filter_signal"].all()


# === exit_signal ===


def test_exit_signal_evaluated():
    strategy = {
        "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}]},
        "exit_signal": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": "<"}],
        },
    }
    df = _df([100] * 5 + [90])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["exit_signal"].iloc[5]


def test_no_exit_signal_default_false():
    strategy = {
        "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}]}
    }
    df = _df([100, 100, 100, 110])
    result = StrategyEngine(strategy).generate_signals(df)
    assert not result["exit_signal"].any()


# === GROUP logic ===


def test_group_logic_or_of_two_and_groups():
    """(A AND B) OR (C AND D) 표현.

    A=가격>MA, B=거래량>=2배 → 둘 다 True여야 그룹1 True
    C=가격<MA, D=거래량<=0.5배 → 둘 다 True여야 그룹2 True
    """
    strategy = {
        "entry": {
            "logic": "GROUP",
            "operator": "OR",
            "groups": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                        {"type": "volume_ratio", "period": 5, "operator": ">=", "value": 2.0},
                    ],
                },
                {
                    "logic": "AND",
                    "conditions": [
                        {"type": "price_vs_ma", "ma_period": 5, "operator": "<"},
                        {"type": "volume_ratio", "period": 5, "operator": "<=", "value": 0.5},
                    ],
                },
            ],
        }
    }
    # 그룹1을 만족하는 데이터: 마지막에 가격 급등 + 거래량 급증
    df = _df([100] * 5 + [110], volume=[100] * 5 + [500])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["entry_signal"].iloc[5]


def test_group_invalid_operator_raises():
    strategy = {
        "entry": {
            "logic": "GROUP",
            "operator": "XOR",
            "groups": [
                {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}]}
            ],
        }
    }
    df = _df([100, 101, 102, 103])
    with pytest.raises(ValueError):
        StrategyEngine(strategy).generate_signals(df)


def test_group_empty_groups_returns_true_series():
    strategy = {"entry": {"logic": "GROUP", "operator": "OR", "groups": []}}
    df = _df([100, 101, 102])
    result = StrategyEngine(strategy).generate_signals(df)
    assert result["entry_signal"].all()


# === 라우팅 / 오류 ===


def test_unknown_condition_type_raises():
    strategy = {"entry": {"logic": "AND", "conditions": [{"type": "not_registered"}]}}
    df = _df([100, 101, 102])
    with pytest.raises(UnknownConditionTypeError):
        StrategyEngine(strategy).generate_signals(df)


def test_position_condition_in_entry_raises():
    """take_profit은 포지션 조건 → entry에 들어가면 PositionConditionMisuseError.

    (schema validator가 먼저 잡아야 하지만 registry가 런타임 방어)
    """
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "take_profit", "percent": 7}],
        }
    }
    df = _df([100, 101, 102])
    with pytest.raises(PositionConditionMisuseError):
        StrategyEngine(strategy).generate_signals(df)


def test_position_condition_in_exit_signal_raises():
    """exit_signal에 포지션 조건이 들어간 경우도 동일하게 차단."""
    strategy = {
        "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}]},
        "exit_signal": {
            "logic": "AND",
            "conditions": [{"type": "take_profit", "percent": 7}],
        },
    }
    df = _df([100, 101, 102, 103])
    with pytest.raises(PositionConditionMisuseError):
        StrategyEngine(strategy).generate_signals(df)


def test_invalid_logic_raises():
    strategy = {
        "entry": {
            "logic": "XOR",
            "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}],
        }
    }
    df = _df([100, 101, 102, 110])
    with pytest.raises(ValueError):
        StrategyEngine(strategy).generate_signals(df)


# === 결정론 ===


def test_same_input_same_output():
    """동일 입력 5회 반복 시 동일 출력 (결정론 보장)."""
    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"},
                {"type": "rsi_level", "period": 14, "operator": "<=", "value": 70},
            ],
        }
    }
    rng = np.random.default_rng(42)
    df = pd.DataFrame(
        {
            "adj_close": rng.normal(loc=100, scale=2, size=50).cumsum() + 100,
            "adj_volume": rng.uniform(1000, 5000, size=50),
        }
    )

    engine = StrategyEngine(strategy)
    base = engine.generate_signals(df)
    for _ in range(4):
        again = engine.generate_signals(df)
        pd.testing.assert_frame_equal(base, again)


# === 입력 보존 ===


def test_input_df_not_mutated():
    """generate_signals는 df를 복사해 작업해야 한다 (원본 보존)."""
    strategy = {
        "entry": {"logic": "AND", "conditions": [{"type": "price_vs_ma", "ma_period": 3, "operator": ">"}]}
    }
    df = _df([100, 101, 102, 103])
    original_columns = set(df.columns)

    StrategyEngine(strategy).generate_signals(df)

    assert set(df.columns) == original_columns
