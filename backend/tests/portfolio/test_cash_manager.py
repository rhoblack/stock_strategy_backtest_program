"""CashManager 단위 테스트."""

from datetime import date

import pytest

from app.backtest.execution import ExecutionModel
from app.portfolio.cash_manager import CashManager
from app.portfolio.portfolio import Portfolio


def _portfolio_with_two_positions() -> Portfolio:
    p = Portfolio(initial_cash=100_000)
    # cash 100,000 → 두 매수로 cash 0 만들기
    p.buy(symbol="A", price=10_000, quantity=5, on_date=date(2024, 1, 1))  # cash 50,000
    p.buy(symbol="B", price=10_000, quantity=5, on_date=date(2024, 1, 2))  # cash 0
    return p


def test_disabled_when_rule_none():
    cm = CashManager(None)
    assert cm.enabled is False
    p = Portfolio(initial_cash=0)
    assert cm.handle_shortage(p, 1, date(2024, 1, 1), lambda *_: 100) == []


def test_disabled_when_explicitly_disabled():
    cm = CashManager({"enabled": False})
    assert cm.enabled is False


def test_no_action_when_cash_sufficient():
    cm = CashManager({"enabled": True, "shortage_rule": {}})
    p = Portfolio(initial_cash=100)
    events = cm.handle_shortage(p, required_cash=50, on_date=date(2024, 1, 1), price_provider=lambda *_: 10)
    assert events == []


def test_lowest_return_partial_sell():
    """A는 +20% (price 12000), B는 -10% (price 9000) → lowest_return은 B."""
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 12_000)
    p.update_market_price("B", 9_000)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
                "repeat_until_cash_sufficient": False,
            },
        }
    )
    events = cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 1, 5),
        price_provider=lambda s, _d: 9_000 if s == "B" else 12_000,
    )
    assert len(events) == 1
    assert events[0]["symbol"] == "B"
    assert events[0]["sell_quantity"] == 2  # 5 * 0.4
    assert events[0]["cash_after"] >= events[0]["cash_before"]


def test_largest_value():
    """A는 12,000원 5주=60,000 / B는 9,000원 5주=45,000 → A가 largest_value."""
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 12_000)
    p.update_market_price("B", 9_000)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "largest_value"},
            },
        }
    )
    events = cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 1, 5),
        price_provider=lambda s, _d: 12_000 if s == "A" else 9_000,
    )
    assert events[0]["symbol"] == "A"


def test_repeat_until_sufficient():
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
                "repeat_until_cash_sufficient": True,
            },
        }
    )
    events = cm.handle_shortage(
        p,
        required_cash=30_000,
        on_date=date(2024, 1, 5),
        price_provider=lambda *_: 10_000,
    )
    assert len(events) >= 2  # 한 번에 부족하면 추가 매도
    assert p.cash >= 30_000


def test_unknown_method_raises():
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.5},
                "target_selection": {"method": "x"},
            },
        }
    )
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)
    with pytest.raises(ValueError):
        cm.handle_shortage(p, 999_999, date(2024, 1, 5), lambda *_: 10_000)


# === 리뷰 011 C2: ExecutionModel 주입 시 슬리피지/세금 적용 ===


def test_forced_sell_applies_slippage_and_tax_when_execution_model_injected():
    """ExecutionModel 주입 시 강제 매도 net_amount < raw_price * qty.

    슬리피지(매도는 가격 인하) + 거래세 + 수수료가 적용되어 net이 줄어들어야 함.
    """
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)

    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.001)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
            },
        },
        execution_model=em,
    )

    raw_price = 10_000
    qty = 2  # 5 * 0.4
    events = cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 6, 1),
        price_provider=lambda *_: raw_price,
    )
    assert len(events) == 1
    ev = events[0]
    raw_proceeds = raw_price * qty  # 20,000
    assert ev["net_amount"] < raw_proceeds, (
        "ExecutionModel 적용 시 net_amount는 raw_price*qty보다 작아야 한다 "
        "(슬리피지+세금)"
    )
    # fee/tax 분해가 0보다 큼
    assert ev["fee"] > 0
    assert ev["tax"] > 0
    # 슬리피지로 인해 exec_price가 raw_price보다 낮음
    assert ev["exec_price"] < raw_price


def test_forced_sell_legacy_fallback_when_no_execution_model():
    """ExecutionModel 미주입 시 raw price 그대로 매도 (레거시 fallback)."""
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)

    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
            },
        },
        # execution_model=None (default)
    )

    raw_price = 10_000
    qty = 2
    events = cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 6, 1),
        price_provider=lambda *_: raw_price,
    )
    ev = events[0]
    assert ev["net_amount"] == raw_price * qty
    assert ev["fee"] == 0.0
    assert ev["tax"] == 0.0


def test_forced_sell_records_fee_tax_in_trade_logs():
    """ExecutionModel 주입 시 portfolio.trade_logs에도 fee/tax가 기록됨."""
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)

    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.001)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
            },
        },
        execution_model=em,
    )
    cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 6, 1),
        price_provider=lambda *_: 10_000,
    )

    sell_logs = [t for t in p.trade_logs if t.get("execution_type") in ("SELL", "PARTIAL_SELL")]
    assert len(sell_logs) >= 1
    log = sell_logs[-1]
    assert log["reason"] == "cash_shortage_partial_sell"
    assert log["fee"] > 0
    assert log["tax"] > 0
    assert log["net_amount"] == log["gross_amount"] - log["fee"] - log["tax"]


def test_cash_manager_uses_execution_model_via_spy():
    """ExecutionModel.calculate_sell_proceeds가 호출되는지 spy로 검증."""
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 10_000)
    p.update_market_price("B", 10_000)

    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.001)
    call_log: list[tuple] = []

    original = em.calculate_sell_proceeds

    def spy(price, quantity, on_date, *, raw_price=None):
        call_log.append((price, quantity, on_date, raw_price))
        return original(price, quantity, on_date, raw_price=raw_price)

    em.calculate_sell_proceeds = spy  # type: ignore[method-assign]

    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
            },
        },
        execution_model=em,
    )
    cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=date(2024, 6, 1),
        price_provider=lambda *_: 10_000,
    )
    assert len(call_log) == 1
    # raw_price가 제대로 전달됨
    assert call_log[0][3] == 10_000


# ========================================================================
# 015) CashManager 강제 매도는 today 즉시 체결 — signal_date == execution_date
# ========================================================================


def test_forced_sell_records_signal_date_equals_execution_date():
    """CashManager 강제 매도(cash_shortage_partial_sell)는 그 시점에 즉시 체결.

    BacktestEngine이 next_open 매수 직전 부족분을 채우려 호출하므로 signal_date /
    execution_date / trade_logs.date 모두 today(=on_date)로 동일해야 한다.
    015 정합성 수정 후에도 cash_manager 경로는 변경되지 않음을 회귀 보증.
    """
    p = _portfolio_with_two_positions()
    p.update_market_price("A", 12_000)
    p.update_market_price("B", 9_000)
    em = ExecutionModel(fee_rate=0.001, tax_rate=0.0018, slippage=0.001)
    cm = CashManager(
        {
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.4},
                "target_selection": {"method": "lowest_return"},
            },
        },
        execution_model=em,
    )
    on_date = date(2024, 6, 1)
    cm.handle_shortage(
        p,
        required_cash=10_000,
        on_date=on_date,
        price_provider=lambda s, _d: 9_000 if s == "B" else 12_000,
    )

    sell_logs = [
        log for log in p.trade_logs if log.get("reason") == "cash_shortage_partial_sell"
    ]
    assert len(sell_logs) == 1
    log = sell_logs[0]
    # 강제 매도는 즉시 체결 — signal_date == execution_date == on_date
    assert log["execution_date"] == on_date
    assert log["signal_date"] == on_date
    assert log["date"] == on_date
