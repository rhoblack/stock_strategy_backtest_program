"""Position + TradeGroup 테스트."""

from datetime import date

import pytest

from app.portfolio.position import Position, TradeGroup


def _tg(tg_id: int, entry_date: date, entry_price: float, qty: int, remaining: int | None = None) -> TradeGroup:
    return TradeGroup(
        trade_group_id=tg_id,
        entry_date=entry_date,
        entry_price=entry_price,
        entry_quantity=qty,
        remaining_quantity=qty if remaining is None else remaining,
    )


# === 단일 trade_group ===


def test_position_single_trade_group_basic_props():
    pos = Position(symbol="005930", current_price=11_000, trade_groups=[
        _tg(1, date(2024, 1, 10), entry_price=10_000, qty=10),
    ])
    assert pos.quantity == 10
    assert pos.avg_entry_price == 10_000
    assert pos.market_value == 110_000
    assert pos.unrealized_profit == 10_000  # (11_000 - 10_000) * 10
    assert pos.unrealized_return_pct == pytest.approx(10.0)


def test_position_first_entry_date_with_one_group():
    pos = Position(symbol="005930", trade_groups=[_tg(1, date(2024, 1, 10), 10_000, 10)])
    assert pos.first_entry_date == date(2024, 1, 10)


def test_position_first_entry_date_empty_raises():
    pos = Position(symbol="005930")
    with pytest.raises(ValueError):
        _ = pos.first_entry_date


# === 다중 trade_group (가중평균) ===


def test_position_multiple_trade_groups_weighted_average_price():
    """평단가 = (10*1000 + 20*1500) / 30 = 1333.33"""
    pos = Position(symbol="005930", trade_groups=[
        _tg(1, date(2024, 1, 10), entry_price=1_000, qty=10),
        _tg(2, date(2024, 1, 20), entry_price=1_500, qty=20),
    ])
    assert pos.quantity == 30
    expected_avg = (10 * 1_000 + 20 * 1_500) / 30
    assert pos.avg_entry_price == pytest.approx(expected_avg)


def test_position_first_entry_date_picks_oldest():
    pos = Position(symbol="005930", trade_groups=[
        _tg(1, date(2024, 1, 20), 1_000, 10),
        _tg(2, date(2024, 1, 10), 1_500, 20),  # 더 오래됨
    ])
    assert pos.first_entry_date == date(2024, 1, 10)


# === 부분 매도 후 평단가 유지 ===


def test_partial_sell_does_not_change_avg_entry_price():
    """부분 매도 후 trade_group.entry_price는 변경되지 않음 (정확성 정책 13.9.3)."""
    pos = Position(symbol="005930", trade_groups=[
        _tg(1, date(2024, 1, 10), entry_price=10_000, qty=10, remaining=10),
    ])
    avg_before = pos.avg_entry_price

    # 부분 매도 시뮬레이션 (Portfolio 거치지 않고 직접)
    pos.trade_groups[0].remaining_quantity -= 3

    assert pos.quantity == 7
    assert pos.avg_entry_price == avg_before  # 평단가 유지


def test_avg_price_zero_when_quantity_zero():
    pos = Position(symbol="005930")
    assert pos.avg_entry_price == 0.0
    assert pos.unrealized_return_pct == 0.0


# === current_price 변동 ===


def test_unrealized_return_pct_negative_on_price_drop():
    pos = Position(symbol="005930", current_price=8_000, trade_groups=[
        _tg(1, date(2024, 1, 10), 10_000, 10),
    ])
    assert pos.unrealized_return_pct == pytest.approx(-20.0)
    assert pos.unrealized_profit == pytest.approx(-20_000)
