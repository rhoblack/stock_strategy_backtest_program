"""CashManager 단위 테스트."""

from datetime import date

import pytest

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
