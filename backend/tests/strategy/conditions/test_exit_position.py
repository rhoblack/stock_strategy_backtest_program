"""take_profit 포지션 조건 테스트.

`Position` / `MarketRow` 인터페이스는 Step 7에서 정식화되므로 여기서는
duck typing으로 mock 객체를 만들어 검증한다.
"""

from types import SimpleNamespace

import pytest

from app.strategy.conditions.exit_position import TAKE_PROFIT_META, take_profit
from app.strategy.registry import condition_registry


def _position(entry_price: float):
    return SimpleNamespace(entry_price=entry_price)


# === intraday_high 트리거 (기본) ===


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


# === close 트리거 ===


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


# === 잘못된 파라미터 ===


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


# === Registry 라우팅 ===


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


# === META ===


def test_take_profit_meta_required_fields():
    for key in ("type", "category", "requires_position", "parameters", "allowed_in"):
        assert key in TAKE_PROFIT_META
    assert TAKE_PROFIT_META["requires_position"] is True
    assert TAKE_PROFIT_META["allowed_in"] == ["exit_position"]
