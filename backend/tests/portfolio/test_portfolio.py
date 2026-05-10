"""Portfolio 매수/매도/평단가/FIFO 테스트."""

from datetime import date

import pytest

from app.backtest.execution import ExecutionModel, ExecutionResult
from app.portfolio.portfolio import Portfolio

# === 기본 ===


def test_initial_state():
    p = Portfolio(initial_cash=10_000_000)
    assert p.cash == 10_000_000
    assert p.initial_cash == 10_000_000
    assert p.positions == {}
    assert p.total_stock_value() == 0
    assert p.total_equity() == 10_000_000
    assert p.positions_count() == 0


def test_negative_initial_cash_raises():
    with pytest.raises(ValueError):
        Portfolio(initial_cash=-1)


# === 매수 ===


def test_buy_creates_position_and_decreases_cash():
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    assert tg_id == 1
    assert p.cash == 900_000
    assert p.positions_count() == 1
    pos = p.positions["005930"]
    assert pos.quantity == 10
    assert pos.avg_entry_price == 10_000
    assert pos.peak_price == 10_000


def test_buy_with_cost_override_uses_actual_cost():
    p = Portfolio(initial_cash=1_000_000)
    p.buy(
        symbol="005930",
        price=10_000,
        quantity=10,
        on_date=date(2024, 1, 10),
        cost_override=100_150,  # 수수료 포함
    )
    assert p.cash == 1_000_000 - 100_150


def test_buy_insufficient_cash_raises():
    p = Portfolio(initial_cash=50_000)
    with pytest.raises(ValueError):
        p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))


def test_buy_negative_quantity_raises():
    p = Portfolio(initial_cash=1_000_000)
    with pytest.raises(ValueError):
        p.buy(symbol="005930", price=10_000, quantity=-1, on_date=date(2024, 1, 10))


def test_buy_existing_symbol_without_pyramiding_raises():
    p = Portfolio(initial_cash=1_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    with pytest.raises(ValueError, match="추가매수가 비활성화"):
        p.buy(symbol="005930", price=11_000, quantity=5, on_date=date(2024, 1, 11))


def test_buy_existing_symbol_with_pyramiding_adds_trade_group():
    p = Portfolio(initial_cash=1_000_000)
    tg1 = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    tg2 = p.buy(
        symbol="005930",
        price=12_000,
        quantity=5,
        on_date=date(2024, 1, 15),
        allow_pyramiding=True,
    )
    assert tg1 != tg2
    pos = p.positions["005930"]
    assert pos.quantity == 15
    # 가중평균: (10*10000 + 5*12000) / 15
    assert pos.avg_entry_price == pytest.approx((10 * 10_000 + 5 * 12_000) / 15)


def test_trade_group_ids_are_monotonic():
    p = Portfolio(initial_cash=10_000_000)
    id1 = p.buy(symbol="A", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    id2 = p.buy(symbol="B", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    id3 = p.buy(symbol="C", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    assert (id1, id2, id3) == (1, 2, 3)


# === 매도: trade_group 단위 ===


def test_sell_trade_group_full_removes_group():
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.sell_trade_group(
        symbol="005930",
        trade_group_id=tg_id,
        price=11_000,
        quantity=10,
        on_date=date(2024, 1, 20),
        reason="take_profit",
    )
    # 포지션 자체가 제거됨
    assert "005930" not in p.positions
    assert p.cash == 1_000_000 - 10_000 * 10 + 11_000 * 10  # 1_010_000


def test_sell_trade_group_partial_keeps_group():
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.sell_trade_group(
        symbol="005930",
        trade_group_id=tg_id,
        price=11_000,
        quantity=4,
        on_date=date(2024, 1, 15),
        reason="cash_shortage_partial_sell",
    )
    pos = p.positions["005930"]
    assert pos.quantity == 6
    assert pos.trade_groups[0].entry_price == 10_000  # 평단가 유지
    assert pos.trade_groups[0].remaining_quantity == 6
    last_log = p.trade_logs[-1]
    assert last_log["execution_type"] == "PARTIAL_SELL"
    assert last_log["is_partial"] is True


def test_sell_trade_group_records_realized_profit():
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.sell_trade_group(
        symbol="005930",
        trade_group_id=tg_id,
        price=11_500,
        quantity=10,
        on_date=date(2024, 1, 20),
        reason="take_profit",
    )
    log = p.trade_logs[-1]
    assert log["realized_profit"] == pytest.approx((11_500 - 10_000) * 10)
    assert log["realized_profit_rate"] == pytest.approx(15.0)


def test_sell_unknown_symbol_raises():
    p = Portfolio(initial_cash=1_000_000)
    with pytest.raises(ValueError):
        p.sell_trade_group(
            symbol="X", trade_group_id=1, price=1, quantity=1, on_date=date(2024, 1, 10), reason="x"
        )


def test_sell_unknown_trade_group_id_raises():
    p = Portfolio(initial_cash=1_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    with pytest.raises(ValueError):
        p.sell_trade_group(
            symbol="005930",
            trade_group_id=999,
            price=11_000,
            quantity=5,
            on_date=date(2024, 1, 11),
            reason="x",
        )


# === FIFO 매도 ===


def test_sell_symbol_fifo_takes_oldest_first():
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.buy(
        symbol="005930",
        price=12_000,
        quantity=5,
        on_date=date(2024, 1, 20),
        allow_pyramiding=True,
    )
    # 12주 매도 → 첫 lot 10주 전량 + 두 번째 lot 2주
    logs = p.sell_symbol_fifo(
        symbol="005930",
        price=15_000,
        quantity=12,
        on_date=date(2024, 2, 1),
        reason="exit_signal",
    )
    assert len(logs) == 2
    assert logs[0]["trade_group_id"] == 1
    assert logs[0]["quantity"] == 10
    assert logs[1]["trade_group_id"] == 2
    assert logs[1]["quantity"] == 2

    # 잔존: 두 번째 lot 3주
    pos = p.positions["005930"]
    assert pos.quantity == 3
    assert pos.trade_groups[0].trade_group_id == 2
    assert pos.trade_groups[0].remaining_quantity == 3


def test_sell_symbol_fifo_full_clears_position():
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.sell_symbol_fifo(
        symbol="005930",
        price=11_000,
        quantity=10,
        on_date=date(2024, 1, 20),
        reason="exit_signal",
    )
    assert "005930" not in p.positions


def test_sell_symbol_fifo_more_than_held_raises():
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    with pytest.raises(ValueError):
        p.sell_symbol_fifo(
            symbol="005930",
            price=11_000,
            quantity=11,
            on_date=date(2024, 1, 20),
            reason="x",
        )


def test_sell_symbol_fifo_proceeds_override_distributed_proportionally():
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.buy(
        symbol="005930",
        price=12_000,
        quantity=10,
        on_date=date(2024, 1, 20),
        allow_pyramiding=True,
    )
    cash_before = p.cash
    # 15주를 총 195,000원에 매도 (수수료/세금 반영된 순수익)
    # FIFO: tg1 10주 + tg2 5주 → 비례 분배: tg1 130,000 + tg2 65,000
    logs = p.sell_symbol_fifo(
        symbol="005930",
        price=13_000,
        quantity=15,
        on_date=date(2024, 2, 1),
        reason="exit_signal",
        proceeds_override=195_000,
    )
    total_proceeds = sum(log["proceeds"] for log in logs)
    assert total_proceeds == pytest.approx(195_000)
    assert p.cash == pytest.approx(cash_before + 195_000)


# === 평가 갱신 ===


def test_update_market_price_updates_current_only_not_peak():
    """정확성 정책 13.3.5 / 13.15: update_market_price는 current_price만 갱신.

    peak_price는 그날 high가 평가 시점에 반영되면 안 되므로(look-ahead 방지)
    update_peak_price로 별도 호출돼야 한다.
    """
    p = Portfolio(initial_cash=1_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))

    # peak는 buy 시점의 entry_price로 초기화돼 있음
    pos = p.positions["005930"]
    assert pos.peak_price == 10_000

    # update_market_price만 호출 → current_price만 변경, peak는 그대로
    p.update_market_price("005930", 12_000)
    assert pos.current_price == 12_000
    assert pos.peak_price == 10_000  # peak 미변경

    # 다음 날 update_peak_price로 그날 high 반영
    p.update_peak_price("005930", 13_000)
    assert pos.peak_price == 13_000

    # 다음 날 high가 더 낮으면 peak 유지
    p.update_peak_price("005930", 11_000)
    assert pos.peak_price == 13_000


def test_update_peak_price_unknown_symbol_noop():
    p = Portfolio(initial_cash=1_000_000)
    # 보유 안 한 종목 → no-op (예외 안 남)
    p.update_peak_price("XXXX", 100_000)


def test_update_market_price_unknown_symbol_noop():
    p = Portfolio(initial_cash=1_000_000)
    # 보유 안 한 종목 → no-op (예외 안 남)
    p.update_market_price("XXXX", 100_000)


def test_position_entry_price_alias_returns_avg_entry_price():
    """포지션 조건 함수가 사용하는 entry_price는 avg_entry_price 별칭."""
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    pos = p.positions["005930"]
    assert pos.entry_price == pos.avg_entry_price == 10_000

    p.buy(
        symbol="005930",
        price=12_000,
        quantity=10,
        on_date=date(2024, 1, 15),
        allow_pyramiding=True,
    )
    # 가중평균 11,000
    assert pos.entry_price == pytest.approx(11_000.0)


# === 자산 계산 ===


def test_total_equity_includes_cash_and_positions():
    p = Portfolio(initial_cash=1_000_000)
    p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 1, 10))
    p.update_market_price("005930", 12_000)

    assert p.cash == 900_000
    assert p.total_stock_value() == 120_000
    assert p.total_equity() == 1_020_000


def test_positions_count_reflects_unique_symbols():
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="A", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    p.buy(symbol="B", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    p.buy(symbol="C", price=1_000, quantity=10, on_date=date(2024, 1, 10))
    assert p.positions_count() == 3


# === ExecutionResult 통합 (리뷰 011 H1 + M2 + M4) ===


def test_buy_with_execution_result_records_fee_breakdown():
    """ExecutionResult로 buy() 호출 시 trade_logs에 fee/tax/gross/net 기록됨."""
    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0023, slippage=0.0)
    p = Portfolio(initial_cash=1_000_000)
    execution = em.calculate_buy_cost(price=10_000, quantity=10)
    p.buy(
        symbol="005930",
        price=10_000,
        quantity=10,
        on_date=date(2024, 6, 10),
        execution=execution,
    )
    log = p.trade_logs[-1]
    assert log["execution_type"] == "BUY"
    assert log["side"] == "buy"
    assert log["gross_amount"] == pytest.approx(100_000)
    assert log["fee"] == pytest.approx(15.0)
    assert log["tax"] == 0.0
    assert log["net_amount"] == pytest.approx(100_015)
    # 호환 키 cost도 net과 동일
    assert log["cost"] == pytest.approx(100_015)
    assert p.cash == pytest.approx(1_000_000 - 100_015)


def test_sell_with_execution_result_records_fee_tax_breakdown():
    """ExecutionResult로 sell_trade_group() 호출 시 fee/tax 분해 기록."""
    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.0)
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 6, 1))
    sell_exec = em.calculate_sell_proceeds(
        price=11_000, quantity=10, on_date=date(2024, 6, 20)
    )
    p.sell_trade_group(
        symbol="005930",
        trade_group_id=tg_id,
        price=11_000,
        quantity=10,
        on_date=date(2024, 6, 20),
        reason="take_profit",
        execution=sell_exec,
    )
    log = p.trade_logs[-1]
    assert log["execution_type"] == "SELL"
    assert log["side"] == "sell"
    assert log["gross_amount"] == pytest.approx(110_000)
    assert log["fee"] == pytest.approx(110_000 * 0.00015)
    assert log["tax"] == pytest.approx(110_000 * 0.0018)
    assert log["net_amount"] == pytest.approx(110_000 - 110_000 * 0.00015 - 110_000 * 0.0018)


def test_realized_profit_uses_net_amount_when_execution_passed():
    """리뷰 011 M2: realized_profit/_rate가 ExecutionResult.net_amount 기반.

    수수료/세금 차감된 net 기준이라 raw price 기반보다 작아야 한다.
    """
    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.0)
    p = Portfolio(initial_cash=1_000_000)
    tg_id = p.buy(symbol="005930", price=10_000, quantity=10, on_date=date(2024, 6, 1))
    sell_exec = em.calculate_sell_proceeds(
        price=11_000, quantity=10, on_date=date(2024, 6, 20)
    )
    p.sell_trade_group(
        symbol="005930",
        trade_group_id=tg_id,
        price=11_000,
        quantity=10,
        on_date=date(2024, 6, 20),
        reason="take_profit",
        execution=sell_exec,
    )
    log = p.trade_logs[-1]

    # raw 기반은 (11000-10000)*10 = 10,000 / 10%
    # net 기반은 net_amount - cost_basis (cost_basis=10000*10=100000)
    expected_profit = sell_exec.net_amount - 100_000
    expected_rate = expected_profit / 100_000 * 100
    assert log["realized_profit"] == pytest.approx(expected_profit)
    assert log["realized_profit_rate"] == pytest.approx(expected_rate)
    # raw 기반보다 작아야 함 (M2)
    assert log["realized_profit"] < (11_000 - 10_000) * 10


def test_buy_with_wrong_side_execution_result_raises():
    p = Portfolio(initial_cash=1_000_000)
    sell_res = ExecutionResult(
        side="sell",
        raw_price=10_000,
        price=10_000,
        quantity=10,
        gross_amount=100_000,
        fee=0,
        tax=0,
        net_amount=100_000,
        slippage_applied=0,
    )
    with pytest.raises(ValueError, match="sell ExecutionResult"):
        p.buy(
            symbol="X",
            price=10_000,
            quantity=10,
            on_date=date(2024, 1, 1),
            execution=sell_res,
        )


def test_sell_fifo_with_execution_result_distributes_fee_proportionally():
    """sell_symbol_fifo + ExecutionResult: fee/tax도 비례 분배되어야 함."""
    em = ExecutionModel(fee_rate=0.001, tax_rate=0.002, slippage=0.0)
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="A", price=10_000, quantity=10, on_date=date(2024, 6, 1))
    p.buy(
        symbol="A",
        price=12_000,
        quantity=10,
        on_date=date(2024, 6, 5),
        allow_pyramiding=True,
    )
    # 15주 매도 (FIFO: tg1 10 + tg2 5)
    sell_exec = em.calculate_sell_proceeds(
        price=13_000, quantity=15, on_date=date(2024, 7, 1)
    )
    logs = p.sell_symbol_fifo(
        symbol="A",
        price=13_000,
        quantity=15,
        on_date=date(2024, 7, 1),
        reason="exit_signal",
        execution=sell_exec,
    )
    assert len(logs) == 2
    # 비례 분배 검증
    total_fee = sum(log["fee"] for log in logs)
    total_tax = sum(log["tax"] for log in logs)
    total_net = sum(log["net_amount"] for log in logs)
    assert total_fee == pytest.approx(sell_exec.fee)
    assert total_tax == pytest.approx(sell_exec.tax)
    assert total_net == pytest.approx(sell_exec.net_amount)
    # 첫 lot은 10주 → 2/3, 두 번째 lot은 5주 → 1/3
    assert logs[0]["quantity"] == 10
    assert logs[1]["quantity"] == 5
    assert logs[0]["fee"] == pytest.approx(sell_exec.fee * 10 / 15)


def test_sell_fifo_execution_quantity_mismatch_raises():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    p = Portfolio(initial_cash=10_000_000)
    p.buy(symbol="A", price=10_000, quantity=10, on_date=date(2024, 6, 1))
    sell_exec = em.calculate_sell_proceeds(price=11_000, quantity=5, on_date=date(2024, 6, 10))
    with pytest.raises(ValueError, match="quantity"):
        p.sell_symbol_fifo(
            symbol="A",
            price=11_000,
            quantity=10,  # execution은 5주인데 10주 요청 — 불일치
            on_date=date(2024, 6, 10),
            reason="x",
            execution=sell_exec,
        )
