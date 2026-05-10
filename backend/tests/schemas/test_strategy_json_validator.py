"""StrategyJsonValidator 단위 테스트 (02번 5절 + 03번 4절 + 10번 7.1).

각 에러 코드별 음성 케이스 + 정상 케이스 + 엣지 케이스를 다룬다.
"""

from __future__ import annotations

import pytest

# 조건 등록을 강제하기 위한 import (부수효과)
import app.strategy  # noqa: F401
from app.core.exceptions import (
    AppError,
    ExitPositionInExitSignalError,
    ExitSignalInExitPositionError,
    InvalidOperatorError,
    InvalidParameterValueError,
    InvalidStrategyJsonError,
    MissingRequiredParameterError,
    UnknownConditionTypeError,
)
from app.schemas.strategy_json import validate_strategy_json

# ============================================================================
# 정상 케이스
# ============================================================================


def _minimal_valid() -> dict:
    return {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [{"type": "stop_loss", "percent": 3.0}],
        },
    }


def test_minimal_valid_passes():
    validate_strategy_json(_minimal_valid())


def test_full_strategy_passes():
    """02번 14절 전체 예시 — 모든 섹션 다 채운 케이스."""
    payload = {
        "name": "거래량 돌파 스윙 전략",
        "version": "1.0",
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
                {"type": "volume_ratio", "period": 20, "operator": ">=", "value": 2.0},
                {"type": "rsi_level", "period": 14, "operator": "<=", "value": 70},
            ],
        },
        "exit_signal": {
            "logic": "OR",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 20, "operator": "<"},
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 7, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3, "trigger": "intraday_low"},
                {"type": "max_holding_days", "days": 10},
                {"type": "trailing_stop", "percent": 5},
            ],
        },
        "filters": {
            "logic": "AND",
            "conditions": [
                {"type": "volume_ratio", "period": 20, "operator": ">=", "value": 1.5},
            ],
        },
        "priority": {"method": "trading_value_desc", "tie_breaker": "symbol_asc"},
        "position_sizing": {
            "method": "fixed_amount",
            "amount": 1_000_000,
            "max_positions": 10,
            "max_daily_entries": 3,
            "daily_buy_budget": 1_000_000,
            "allow_pyramiding": False,
        },
        "execution": {
            "entry_price": "next_open",
            "exit_price": "next_open",
            "fee_rate": 0.00015,
            "tax_rate": [
                {"from": "2020-01-01", "rate": 0.0023},
                {"from": "2023-01-01", "rate": 0.0020},
                {"from": "2024-01-01", "rate": 0.0018},
                {"from": "2025-01-01", "rate": 0.0015},
            ],
            "slippage": 0.001,
            "tick_rounding": "buy_up_sell_down",
        },
        "metadata": {"random_seed": 42},
    }
    validate_strategy_json(payload)


def test_group_logic_valid():
    """02번 4절 GROUP 1단계."""
    payload = _minimal_valid()
    payload["entry"] = {
        "logic": "GROUP",
        "operator": "OR",
        "groups": [
            {
                "logic": "AND",
                "conditions": [
                    {"type": "price_vs_ma", "ma_period": 20, "operator": ">"},
                    {"type": "volume_ratio", "period": 20, "operator": ">=", "value": 2.0},
                ],
            },
            {
                "logic": "AND",
                "conditions": [
                    {"type": "rsi_level", "period": 14, "operator": "<=", "value": 30},
                ],
            },
        ],
    }
    validate_strategy_json(payload)


# ============================================================================
# INVALID_STRATEGY_JSON
# ============================================================================


def test_payload_must_be_dict():
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json("not a dict")
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"


def test_entry_section_required():
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json({})
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"


def test_either_exit_signal_or_exit_position_required():
    payload = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 20, "operator": ">"}],
        }
    }
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"
    assert "exit" in exc_info.value.message


def test_entry_conditions_must_have_at_least_one():
    payload = {
        "entry": {"logic": "AND", "conditions": []},
        "exit_position": {
            "logic": "OR",
            "conditions": [{"type": "stop_loss", "percent": 3.0}],
        },
    }
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"
    assert "entry.conditions" in exc_info.value.details[0]["field"]


def test_logic_value_must_be_allowed():
    payload = _minimal_valid()
    payload["entry"]["logic"] = "XOR"
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"


def test_group_must_have_operator_and_groups():
    payload = _minimal_valid()
    payload["entry"] = {"logic": "GROUP", "operator": "AND"}
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"


def test_group_nested_group_rejected():
    """1단계 중첩만 허용 (02번 4절)."""
    payload = _minimal_valid()
    payload["entry"] = {
        "logic": "GROUP",
        "operator": "OR",
        "groups": [
            {
                "logic": "GROUP",  # 중첩 GROUP — 거부
                "operator": "AND",
                "groups": [],
            }
        ],
    }
    with pytest.raises(InvalidStrategyJsonError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_STRATEGY_JSON"
    assert "GROUP" in exc_info.value.message


# ============================================================================
# UNKNOWN_CONDITION_TYPE
# ============================================================================


def test_unknown_condition_type_in_entry():
    payload = _minimal_valid()
    payload["entry"]["conditions"][0]["type"] = "definitely_not_registered"
    with pytest.raises(UnknownConditionTypeError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "UNKNOWN_CONDITION_TYPE"


def test_unknown_condition_type_in_filters():
    payload = _minimal_valid()
    payload["filters"] = {
        "logic": "AND",
        "conditions": [{"type": "no_such_condition"}],
    }
    with pytest.raises(UnknownConditionTypeError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "UNKNOWN_CONDITION_TYPE"


# ============================================================================
# EXIT_POSITION_IN_EXIT_SIGNAL — 포지션 조건이 시계열 섹션에 들어감
# ============================================================================


def test_take_profit_in_exit_signal_rejected():
    payload = _minimal_valid()
    payload["exit_signal"] = {
        "logic": "OR",
        "conditions": [{"type": "take_profit", "percent": 5.0}],
    }
    with pytest.raises(ExitPositionInExitSignalError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_POSITION_IN_EXIT_SIGNAL"


def test_stop_loss_in_entry_rejected():
    payload = _minimal_valid()
    payload["entry"]["conditions"].append({"type": "stop_loss", "percent": 3.0})
    with pytest.raises(ExitPositionInExitSignalError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_POSITION_IN_EXIT_SIGNAL"


def test_max_holding_days_in_filters_rejected():
    payload = _minimal_valid()
    payload["filters"] = {
        "logic": "AND",
        "conditions": [{"type": "max_holding_days", "days": 10}],
    }
    with pytest.raises(ExitPositionInExitSignalError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_POSITION_IN_EXIT_SIGNAL"


def test_trailing_stop_in_exit_signal_rejected():
    payload = _minimal_valid()
    payload["exit_signal"] = {
        "logic": "OR",
        "conditions": [{"type": "trailing_stop", "percent": 5.0}],
    }
    with pytest.raises(ExitPositionInExitSignalError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_POSITION_IN_EXIT_SIGNAL"


# ============================================================================
# EXIT_SIGNAL_IN_EXIT_POSITION — 시계열 조건이 포지션 섹션에 들어감
# ============================================================================


def test_price_vs_ma_in_exit_position_rejected():
    payload = _minimal_valid()
    payload["exit_position"] = {
        "logic": "OR",
        "conditions": [{"type": "price_vs_ma", "ma_period": 20, "operator": "<"}],
    }
    with pytest.raises(ExitSignalInExitPositionError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_SIGNAL_IN_EXIT_POSITION"


def test_rsi_level_in_exit_position_rejected():
    payload = _minimal_valid()
    payload["exit_position"] = {
        "logic": "OR",
        "conditions": [{"type": "rsi_level", "period": 14, "operator": ">=", "value": 70}],
    }
    with pytest.raises(ExitSignalInExitPositionError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "EXIT_SIGNAL_IN_EXIT_POSITION"


# ============================================================================
# operator / parameter
# ============================================================================


def test_invalid_operator():
    payload = _minimal_valid()
    payload["entry"]["conditions"][0]["operator"] = "<>"
    with pytest.raises(InvalidOperatorError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_OPERATOR"


def test_missing_condition_type():
    payload = _minimal_valid()
    payload["entry"]["conditions"][0] = {"ma_period": 20, "operator": ">"}
    with pytest.raises(MissingRequiredParameterError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "MISSING_REQUIRED_PARAMETER"


# ============================================================================
# position_sizing
# ============================================================================


def test_position_sizing_unknown_method():
    payload = _minimal_valid()
    payload["position_sizing"] = {"method": "moonshot"}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_position_sizing_fixed_amount_zero_rejected():
    payload = _minimal_valid()
    payload["position_sizing"] = {"method": "fixed_amount", "amount": 0}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_position_sizing_max_positions_zero_rejected():
    payload = _minimal_valid()
    payload["position_sizing"] = {
        "method": "fixed_amount",
        "amount": 1_000_000,
        "max_positions": 0,
    }
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


# ============================================================================
# execution / tax_rate 시계열
# ============================================================================


def test_execution_negative_fee_rejected():
    payload = _minimal_valid()
    payload["execution"] = {"fee_rate": -0.001}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_execution_invalid_tick_rounding_rejected():
    payload = _minimal_valid()
    payload["execution"] = {"tick_rounding": "moon_round"}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_tax_rate_array_descending_rejected():
    """02번 15절: from 오름차순."""
    payload = _minimal_valid()
    payload["execution"] = {
        "tax_rate": [
            {"from": "2024-01-01", "rate": 0.0018},
            {"from": "2020-01-01", "rate": 0.0023},  # 거꾸로
        ]
    }
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"
    assert "오름차순" in exc_info.value.message


def test_tax_rate_negative_rate_rejected():
    payload = _minimal_valid()
    payload["execution"] = {
        "tax_rate": [{"from": "2020-01-01", "rate": -0.001}]
    }
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_tax_rate_invalid_date_format_rejected():
    payload = _minimal_valid()
    payload["execution"] = {
        "tax_rate": [{"from": "2020/01/01", "rate": 0.0023}]
    }
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_tax_rate_scalar_float_accepted():
    payload = _minimal_valid()
    payload["execution"] = {"tax_rate": 0.0018}
    validate_strategy_json(payload)


# ============================================================================
# priority
# ============================================================================


def test_priority_unknown_method_rejected():
    payload = _minimal_valid()
    payload["priority"] = {"method": "ouija_board"}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


def test_priority_unknown_tie_breaker_rejected():
    payload = _minimal_valid()
    payload["priority"] = {"method": "trading_value_desc", "tie_breaker": "coin_flip"}
    with pytest.raises(InvalidParameterValueError) as exc_info:
        validate_strategy_json(payload)
    assert exc_info.value.code == "INVALID_PARAMETER_VALUE"


# ============================================================================
# 결정론
# ============================================================================


def test_validation_is_deterministic():
    """같은 입력에 대해 같은 결과 — dict 순회 순서에 영향받지 않음."""
    payload = _minimal_valid()
    # 여러 번 호출해도 같은 결과 (정상)
    for _ in range(5):
        validate_strategy_json(payload)


def test_unknown_type_error_message_lists_allowed_sorted():
    """오류 메시지의 허용 목록이 결정론적 순서(정렬)여야 한다."""
    payload = _minimal_valid()
    payload["entry"]["conditions"][0]["type"] = "no_such"
    msgs: list[str] = []
    for _ in range(3):
        try:
            validate_strategy_json(payload)
        except UnknownConditionTypeError as exc:
            msgs.append(exc.details[0]["message"])
    assert len(set(msgs)) == 1, "허용 목록이 호출마다 달라짐 — sorted 누락"


# ============================================================================
# AppError 계층 sanity (envelope handler가 잡아주려면 모두 AppError여야 함)
# ============================================================================


def test_all_validator_errors_are_app_errors():
    error_classes = [
        InvalidStrategyJsonError,
        UnknownConditionTypeError,
        ExitPositionInExitSignalError,
        ExitSignalInExitPositionError,
        InvalidOperatorError,
        InvalidParameterValueError,
        MissingRequiredParameterError,
    ]
    for cls in error_classes:
        assert issubclass(cls, AppError), f"{cls.__name__}이 AppError 하위가 아님"
