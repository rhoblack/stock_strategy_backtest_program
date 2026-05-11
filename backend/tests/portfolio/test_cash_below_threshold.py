"""step 066 - cash_below_threshold 트리거 테스트 (02-t).

02번 설계서 섹션 9: cash_management.shortage_rule.trigger.type = cash_below_threshold
예수금이 절대값 threshold 미만이면 CashManager 발동 -> 포지션 강제 일부 매도.

검증:
    A) trigger_type 속성 + trigger_threshold 속성
    B) is_triggered(): cash < threshold이면 True, >= 이면 False
    C) handle_shortage: cash_below_threshold 발동 시 포지션 매도 실행
    D) cash >= threshold이면 handle_shortage 미발동
    E) threshold=None이면 발동 안함 (보수적)
    F) cash_below_daily_buy_budget (기존) 동작 유지 확인
    G) is_triggered 경계값: 정확히 threshold이면 False (미만이 아님)
"""

from datetime import date

from app.backtest.execution import ExecutionModel
from app.portfolio.cash_manager import CashManager
from app.portfolio.portfolio import Portfolio


def _portfolio_with_position(cash: float = 0.0) -> Portfolio:
    """초기 현금 0으로 포트폴리오 만든 후 직접 cash 설정."""
    p = Portfolio(initial_cash=500_000)
    # 매수하여 cash 줄이기
    p.buy(symbol="A", price=10_000, quantity=40, on_date=date(2024, 1, 1))
    # cash = 500_000 - 400_000 = 100_000
    # cash 강제 조정은 불가하므로 포지션 수량으로 조정
    return p


# ========================================================================
# A: trigger_type + trigger_threshold 속성
# ========================================================================


def test_trigger_type_cash_below_threshold():
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 50_000},
            "action": {"sell_fraction": 0.25},
            "target_selection": {"method": "lowest_return"},
        },
    }
    cm = CashManager(rule)
    assert cm.trigger_type == "cash_below_threshold"
    assert cm.trigger_threshold == 50_000


def test_trigger_type_default_cash_below_daily_buy_budget():
    rule = {
        "enabled": True,
        "shortage_rule": {
            "action": {"sell_fraction": 0.25},
        },
    }
    cm = CashManager(rule)
    assert cm.trigger_type == "cash_below_daily_buy_budget"
    assert cm.trigger_threshold is None


# ========================================================================
# B: is_triggered()
# ========================================================================


def test_is_triggered_cash_below_threshold_true():
    """cash < threshold -> True."""
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 100_000},
            "action": {"sell_fraction": 0.25},
        },
    }
    cm = CashManager(rule)
    p = Portfolio(initial_cash=80_000)  # cash = 80_000 < 100_000
    assert cm.is_triggered(p, required_cash=0) is True


def test_is_triggered_cash_equal_threshold_false():
    """cash == threshold -> False (미만이 아님)."""
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 100_000},
            "action": {"sell_fraction": 0.25},
        },
    }
    cm = CashManager(rule)
    p = Portfolio(initial_cash=100_000)  # cash = 100_000 == threshold
    assert cm.is_triggered(p, required_cash=0) is False


def test_is_triggered_cash_above_threshold_false():
    """cash > threshold -> False."""
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 50_000},
            "action": {"sell_fraction": 0.25},
        },
    }
    cm = CashManager(rule)
    p = Portfolio(initial_cash=100_000)  # cash = 100_000 > 50_000
    assert cm.is_triggered(p, required_cash=0) is False


def test_is_triggered_none_threshold_false():
    """threshold=None -> 발동 안함 (보수적)."""
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold"},  # threshold 없음
            "action": {"sell_fraction": 0.25},
        },
    }
    cm = CashManager(rule)
    p = Portfolio(initial_cash=1)  # 거의 0이지만 threshold=None이면 발동 안함
    assert cm.is_triggered(p, required_cash=0) is False


def test_is_triggered_disabled_false():
    """enabled=False -> 항상 False."""
    cm = CashManager(None)
    p = Portfolio(initial_cash=0)
    assert cm.is_triggered(p, required_cash=1_000_000) is False


# ========================================================================
# C: handle_shortage 발동 -> 포지션 매도
# ========================================================================


def test_handle_shortage_triggers_when_cash_below_threshold():
    """cash < threshold이면 handle_shortage가 매도 이벤트를 반환."""
    p = Portfolio(initial_cash=500_000)
    p.buy(symbol="A", price=10_000, quantity=40, on_date=date(2024, 1, 1))
    # cash after buy = 100_000

    # threshold = 200_000 > cash(100_000) -> 발동
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 200_000},
            "action": {"sell_fraction": 0.5},
            "target_selection": {"method": "lowest_return"},
        },
    }
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    cm = CashManager(rule, execution_model=em)

    p.update_market_price("A", 10_000)
    events = cm.handle_shortage(
        p, required_cash=0, on_date=date(2024, 1, 2),
        price_provider=lambda s, _d: 10_000,
    )
    assert len(events) >= 1
    assert events[0]["action"] == "partial_sell"


# ========================================================================
# D: cash >= threshold -> handle_shortage 미발동
# ========================================================================


def test_handle_shortage_not_triggered_when_cash_above_threshold():
    """cash >= threshold이면 handle_shortage 미발동."""
    p = Portfolio(initial_cash=500_000)
    p.buy(symbol="A", price=10_000, quantity=10, on_date=date(2024, 1, 1))
    # cash after buy = 400_000

    # threshold = 200_000 < cash(400_000) -> 미발동
    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_threshold", "threshold": 200_000},
            "action": {"sell_fraction": 0.5},
            "target_selection": {"method": "lowest_return"},
        },
    }
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    cm = CashManager(rule, execution_model=em)

    events = cm.handle_shortage(
        p, required_cash=0, on_date=date(2024, 1, 2),
        price_provider=lambda s, _d: 10_000,
    )
    assert len(events) == 0


# ========================================================================
# F: cash_below_daily_buy_budget 기존 동작 유지
# ========================================================================


def test_cash_below_daily_buy_budget_still_works():
    """기존 cash_below_daily_buy_budget 트리거 동작 유지."""
    p = Portfolio(initial_cash=500_000)
    p.buy(symbol="A", price=10_000, quantity=40, on_date=date(2024, 1, 1))
    # cash = 100_000

    rule = {
        "enabled": True,
        "shortage_rule": {
            "trigger": {"type": "cash_below_daily_buy_budget"},
            "action": {"sell_fraction": 0.5},
            "target_selection": {"method": "lowest_return"},
        },
    }
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    cm = CashManager(rule, execution_model=em)

    # required_cash=200_000 > cash(100_000) -> 발동
    p.update_market_price("A", 10_000)
    events = cm.handle_shortage(
        p, required_cash=200_000, on_date=date(2024, 1, 2),
        price_provider=lambda s, _d: 10_000,
    )
    assert len(events) >= 1

    # required_cash=50_000 < cash -> 미발동
    p2 = Portfolio(initial_cash=500_000)
    p2.buy(symbol="A", price=10_000, quantity=40, on_date=date(2024, 1, 1))
    p2.update_market_price("A", 10_000)
    events2 = cm.handle_shortage(
        p2, required_cash=50_000, on_date=date(2024, 1, 2),
        price_provider=lambda s, _d: 10_000,
    )
    assert len(events2) == 0
