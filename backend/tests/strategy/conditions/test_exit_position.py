"""포지션 매도 조건 테스트 (take_profit / stop_loss / max_holding_days / trailing_stop).

`Position` / `MarketRow` 인터페이스는 Step 7에서 정식화되므로 여기서는
duck typing으로 mock 객체를 만들어 검증한다.

정확성 정책 13.3:
    - 일중 도달 판정 (intraday_high / intraday_low)
    - 동일 봉 stop + take 동시 도달은 BacktestEngine이 우선순위 정렬로 처리.
      각 함수는 자기 조건만 boolean으로 반환.
    - 갭 처리 (gap_down_stop_loss / gap_up_take_profit)는 BacktestEngine 책임.
    - trailing_stop의 peak는 "전일까지의 high" — Portfolio.update_market_price가
      갱신하며 본 함수는 평가만 (look-ahead bias 방지).
"""

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.strategy.conditions.exit_position import (
    MAX_HOLDING_DAYS_META,
    STOP_LOSS_META,
    TAKE_PROFIT_META,
    TRAILING_STOP_META,
    max_holding_days,
    stop_loss,
    take_profit,
    trailing_stop,
)
from app.strategy.registry import condition_registry


def _position(
    entry_price: float = 10000,
    first_entry_date: date | None = None,
    peak_price: float = 0.0,
):
    """duck-typed Position mock."""
    return SimpleNamespace(
        entry_price=entry_price,
        first_entry_date=first_entry_date,
        peak_price=peak_price,
    )


# ============================================================================
# take_profit (기존)
# ============================================================================


def test_take_profit_intraday_high_triggers_at_target():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 11000, "adj_low": 9500, "adj_close": 10800}
    triggered, reason = take_profit(pos, market_row, {"percent": 7})
    assert triggered is True
    assert reason == "take_profit"


def test_take_profit_intraday_high_no_trigger_below_target():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10500, "adj_low": 9500, "adj_close": 10300}
    triggered, reason = take_profit(pos, market_row, {"percent": 7})
    assert triggered is False
    assert reason is None


def test_take_profit_intraday_high_exact_target_triggers():
    """정확히 임계 가격 도달 시 트리거 (>= 비교)."""
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10700, "adj_low": 9000, "adj_close": 10200}
    triggered, _ = take_profit(pos, market_row, {"percent": 7})
    assert triggered is True


def test_take_profit_close_trigger_uses_close_only():
    """trigger=close면 high가 도달해도 종가가 미달이면 트리거 안 함."""
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 12000, "adj_low": 9500, "adj_close": 10500}
    triggered, _ = take_profit(pos, market_row, {"percent": 7, "trigger": "close"})
    assert triggered is False


def test_take_profit_close_triggers_when_close_meets_target():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 12000, "adj_low": 9500, "adj_close": 11000}
    triggered, reason = take_profit(pos, market_row, {"percent": 7, "trigger": "close"})
    assert triggered is True
    assert reason == "take_profit"


def test_take_profit_negative_percent_raises():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 11000, "adj_low": 9500, "adj_close": 10800}
    with pytest.raises(ValueError):
        take_profit(pos, market_row, {"percent": -7})
    with pytest.raises(ValueError):
        take_profit(pos, market_row, {"percent": 0})


def test_take_profit_invalid_trigger_raises():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 11000, "adj_low": 9500, "adj_close": 10800}
    with pytest.raises(ValueError):
        take_profit(pos, market_row, {"percent": 7, "trigger": "premarket"})


def test_take_profit_registered_as_position_condition():
    """take_profit은 requires_position=True로 등록되어야 함."""
    assert condition_registry.is_position_condition("take_profit") is True


def test_take_profit_via_registry_evaluate_position_works():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 11000, "adj_low": 9500, "adj_close": 10800}
    triggered, reason = condition_registry.evaluate_position(
        "take_profit",
        position=pos,
        market_row=market_row,
        condition={"percent": 7},
    )
    assert triggered is True
    assert reason == "take_profit"


def test_take_profit_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in TAKE_PROFIT_META
    assert TAKE_PROFIT_META["requires_position"] is True
    assert TAKE_PROFIT_META["allowed_in"] == ["exit_position"]


# ============================================================================
# stop_loss
# ============================================================================


def test_stop_loss_intraday_low_triggers_at_threshold():
    """매수가 10000, 손절 -3% → 9700. low가 9700 도달 시 트리거."""
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9700, "adj_close": 9800}
    triggered, reason = stop_loss(pos, market_row, {"percent": 3})
    assert triggered is True
    assert reason == "stop_loss"


def test_stop_loss_intraday_low_no_trigger_above_threshold():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9750, "adj_close": 9900}
    triggered, reason = stop_loss(pos, market_row, {"percent": 3})
    assert triggered is False
    assert reason is None


def test_stop_loss_intraday_low_below_threshold_triggers():
    """low가 손절선보다 더 깊이 떨어진 경우도 트리거."""
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9500, "adj_close": 9550}
    triggered, _ = stop_loss(pos, market_row, {"percent": 3})
    assert triggered is True


def test_stop_loss_close_trigger_uses_close_only():
    """trigger=close면 low가 손절선 밑이라도 종가가 위면 트리거 안 함."""
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9500, "adj_close": 9800}
    triggered, _ = stop_loss(pos, market_row, {"percent": 3, "trigger": "close"})
    assert triggered is False


def test_stop_loss_close_triggers_when_close_at_or_below_threshold():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9400, "adj_close": 9700}
    triggered, reason = stop_loss(pos, market_row, {"percent": 3, "trigger": "close"})
    assert triggered is True
    assert reason == "stop_loss"


def test_stop_loss_negative_percent_raises():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9500, "adj_close": 9700}
    with pytest.raises(ValueError):
        stop_loss(pos, market_row, {"percent": -3})
    with pytest.raises(ValueError):
        stop_loss(pos, market_row, {"percent": 0})


def test_stop_loss_invalid_trigger_raises():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9500, "adj_close": 9700}
    with pytest.raises(ValueError):
        stop_loss(pos, market_row, {"percent": 3, "trigger": "afterhours"})


def test_stop_loss_registered_as_position_condition():
    assert condition_registry.is_position_condition("stop_loss") is True


def test_stop_loss_via_registry_evaluate_position_works():
    pos = _position(entry_price=10000)
    market_row = {"adj_high": 10100, "adj_low": 9700, "adj_close": 9800}
    triggered, reason = condition_registry.evaluate_position(
        "stop_loss",
        position=pos,
        market_row=market_row,
        condition={"percent": 3},
    )
    assert triggered is True
    assert reason == "stop_loss"


def test_stop_loss_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in STOP_LOSS_META
    assert STOP_LOSS_META["requires_position"] is True
    assert STOP_LOSS_META["allowed_in"] == ["exit_position"]


# ============================================================================
# stop_loss와 take_profit 동일 봉 동시 도달 — 정확성 정책 13.3.2
# ============================================================================


def test_stop_loss_and_take_profit_both_trigger_independently():
    """동일 봉에서 high가 익절선, low가 손절선에 모두 도달하면
    각 함수는 독립적으로 True를 반환한다.

    어느 쪽을 우선 처리할지 (정책 13.3.2: 손절 우선)는 BacktestEngine의
    rules 순회 순서로 결정한다. 본 단위 테스트는 각 조건의 자기 평가만 검증.
    """
    pos = _position(entry_price=10000)
    # high 11000 (>= 10700 익절선 7%) AND low 9700 (<= 9700 손절선 3%)
    market_row = {"adj_high": 11000, "adj_low": 9700, "adj_close": 10000}

    sl_trig, sl_reason = stop_loss(pos, market_row, {"percent": 3})
    tp_trig, tp_reason = take_profit(pos, market_row, {"percent": 7})

    assert sl_trig is True
    assert sl_reason == "stop_loss"
    assert tp_trig is True
    assert tp_reason == "take_profit"


# ============================================================================
# max_holding_days
# ============================================================================


def test_max_holding_days_triggers_at_threshold():
    """매수 후 정확히 N일 경과 시 트리거."""
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 11),  # 10일 경과
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, reason = max_holding_days(pos, market_row, {"days": 10})
    assert triggered is True
    assert reason == "max_holding_days"


def test_max_holding_days_no_trigger_before_threshold():
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 9),  # 8일 경과
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, reason = max_holding_days(pos, market_row, {"days": 10})
    assert triggered is False
    assert reason is None


def test_max_holding_days_triggers_after_threshold():
    """N일을 초과해도 트리거 (>=)."""
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 6, 1),  # 31일 경과
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, _ = max_holding_days(pos, market_row, {"days": 10})
    assert triggered is True


def test_max_holding_days_uses_pandas_series_index_when_no_date_key():
    """market_row가 pandas Series이고 .name이 Timestamp인 경우도 지원."""
    pos = _position(first_entry_date=date(2026, 5, 1))
    series = pd.Series(
        {"adj_high": 11000, "adj_low": 9500, "adj_close": 10500},
        name=pd.Timestamp("2026-05-15"),
    )
    triggered, _ = max_holding_days(pos, series, {"days": 10})
    assert triggered is True


def test_max_holding_days_handles_pandas_timestamp_first_entry():
    """position.first_entry_date가 pd.Timestamp여도 정상 처리."""
    pos = _position(first_entry_date=pd.Timestamp("2026-05-01"))
    market_row = {
        "date": date(2026, 5, 11),
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, _ = max_holding_days(pos, market_row, {"days": 10})
    assert triggered is True


def test_max_holding_days_zero_or_negative_raises():
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 11),
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    with pytest.raises(ValueError):
        max_holding_days(pos, market_row, {"days": 0})
    with pytest.raises(ValueError):
        max_holding_days(pos, market_row, {"days": -3})


def test_max_holding_days_non_integer_raises():
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 11),
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    with pytest.raises(ValueError):
        max_holding_days(pos, market_row, {"days": 3.5})


def test_max_holding_days_float_integer_value_accepted():
    """JSON에서 들어온 10.0 같은 정수형 float은 허용."""
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 11),
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, _ = max_holding_days(pos, market_row, {"days": 10.0})
    assert triggered is True


def test_max_holding_days_no_date_anywhere_raises():
    pos = _position(first_entry_date=date(2026, 5, 1))
    # dict에 date 키 없고 pandas Series도 아니어서 .name도 없음
    market_row = {"adj_high": 11000, "adj_low": 9500, "adj_close": 10500}
    with pytest.raises(ValueError):
        max_holding_days(pos, market_row, {"days": 10})


def test_max_holding_days_registered_as_position_condition():
    assert condition_registry.is_position_condition("max_holding_days") is True


def test_max_holding_days_via_registry_evaluate_position_works():
    pos = _position(first_entry_date=date(2026, 5, 1))
    market_row = {
        "date": date(2026, 5, 11),
        "adj_high": 11000, "adj_low": 9500, "adj_close": 10500,
    }
    triggered, reason = condition_registry.evaluate_position(
        "max_holding_days",
        position=pos,
        market_row=market_row,
        condition={"days": 10},
    )
    assert triggered is True
    assert reason == "max_holding_days"


def test_max_holding_days_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in MAX_HOLDING_DAYS_META
    assert MAX_HOLDING_DAYS_META["requires_position"] is True
    assert MAX_HOLDING_DAYS_META["allowed_in"] == ["exit_position"]


# ============================================================================
# trailing_stop
# ============================================================================


def test_trailing_stop_intraday_low_triggers_when_low_breaks_threshold():
    """peak 12000, 5% 트레일 → 11400. low가 11400 도달 시 트리거."""
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11500, "adj_low": 11400, "adj_close": 11450}
    triggered, reason = trailing_stop(pos, market_row, {"percent": 5})
    assert triggered is True
    assert reason == "trailing_stop"


def test_trailing_stop_no_trigger_above_threshold():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11800, "adj_low": 11500, "adj_close": 11600}
    triggered, reason = trailing_stop(pos, market_row, {"percent": 5})
    assert triggered is False
    assert reason is None


def test_trailing_stop_close_trigger_uses_close_only():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11800, "adj_low": 11400, "adj_close": 11500}
    # low는 손절선 도달했지만 trigger=close → 종가 11500 > 11400 → 트리거 안 함
    triggered, _ = trailing_stop(pos, market_row, {"percent": 5, "trigger": "close"})
    assert triggered is False


def test_trailing_stop_close_triggers_when_close_at_or_below_threshold():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11800, "adj_low": 11000, "adj_close": 11400}
    triggered, reason = trailing_stop(pos, market_row, {"percent": 5, "trigger": "close"})
    assert triggered is True
    assert reason == "trailing_stop"


def test_trailing_stop_uses_position_peak_only_no_self_update():
    """본 함수가 peak_price를 갱신하지 않는다 (look-ahead bias 방지).

    peak가 12000으로 고정된 상태에서 high가 13000까지 올라가도
    함수 호출 후 position.peak_price는 그대로 12000이어야 한다.
    peak 갱신은 Portfolio.update_market_price 책임.
    """
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 13000, "adj_low": 11500, "adj_close": 12500}
    trailing_stop(pos, market_row, {"percent": 5})
    # 함수 실행 후에도 peak_price는 그대로
    assert pos.peak_price == 12000


def test_trailing_stop_no_peak_does_not_trigger():
    """peak_price가 0이거나 None이면 평가 불가 — False 반환 (보수적)."""
    pos = _position(entry_price=10000, peak_price=0)
    market_row = {"adj_high": 9000, "adj_low": 8000, "adj_close": 8500}
    triggered, reason = trailing_stop(pos, market_row, {"percent": 5})
    assert triggered is False
    assert reason is None


def test_trailing_stop_negative_percent_raises():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11500, "adj_low": 11400, "adj_close": 11450}
    with pytest.raises(ValueError):
        trailing_stop(pos, market_row, {"percent": -5})
    with pytest.raises(ValueError):
        trailing_stop(pos, market_row, {"percent": 0})


def test_trailing_stop_invalid_trigger_raises():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11500, "adj_low": 11400, "adj_close": 11450}
    with pytest.raises(ValueError):
        trailing_stop(pos, market_row, {"percent": 5, "trigger": "premarket"})


def test_trailing_stop_registered_as_position_condition():
    assert condition_registry.is_position_condition("trailing_stop") is True


def test_trailing_stop_via_registry_evaluate_position_works():
    pos = _position(entry_price=10000, peak_price=12000)
    market_row = {"adj_high": 11500, "adj_low": 11400, "adj_close": 11450}
    triggered, reason = condition_registry.evaluate_position(
        "trailing_stop",
        position=pos,
        market_row=market_row,
        condition={"percent": 5},
    )
    assert triggered is True
    assert reason == "trailing_stop"


def test_trailing_stop_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in TRAILING_STOP_META
    assert TRAILING_STOP_META["requires_position"] is True
    assert TRAILING_STOP_META["allowed_in"] == ["exit_position"]


# ============================================================================
# 카탈로그 등록 (condition_definitions.py)
# ============================================================================


def test_all_new_exit_position_conditions_in_catalog():
    """get_condition_catalog()가 새 조건 3종을 모두 노출해야 한다."""
    from app.strategy.condition_definitions import get_condition_catalog

    catalog = get_condition_catalog()
    types = {item["type"] for item in catalog}
    assert "stop_loss" in types
    assert "max_holding_days" in types
    assert "trailing_stop" in types
    assert "take_profit" in types  # 회귀 검증
