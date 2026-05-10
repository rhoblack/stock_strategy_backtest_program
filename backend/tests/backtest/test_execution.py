"""ExecutionModel 테스트 — 정확성 정책 13.5/13.6."""

from datetime import date

import pytest

from app.backtest.execution import ExecutionModel, ExecutionResult, TaxRateEntry

# === 거래세 시계열 ===


def _kr_tax_history() -> list[dict]:
    """한국 거래세 변동 이력 (정확성 정책 13.6.1)."""
    return [
        {"from": "2020-01-01", "rate": 0.0023},
        {"from": "2023-01-01", "rate": 0.0020},
        {"from": "2024-01-01", "rate": 0.0018},
        {"from": "2025-01-01", "rate": 0.0015},
    ]


def test_tax_rate_scalar_constant():
    em = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.001)
    assert em.get_tax_rate(date(2020, 1, 1)) == pytest.approx(0.0018)
    assert em.get_tax_rate(date(2025, 12, 31)) == pytest.approx(0.0018)


def test_tax_rate_timeseries_each_period():
    em = ExecutionModel(fee_rate=0.00015, tax_rate=_kr_tax_history(), slippage=0.001)
    assert em.get_tax_rate(date(2022, 12, 31)) == pytest.approx(0.0023)
    assert em.get_tax_rate(date(2023, 6, 15)) == pytest.approx(0.0020)
    assert em.get_tax_rate(date(2024, 6, 15)) == pytest.approx(0.0018)
    assert em.get_tax_rate(date(2025, 6, 15)) == pytest.approx(0.0015)


def test_tax_rate_before_first_entry_returns_zero():
    em = ExecutionModel(fee_rate=0.00015, tax_rate=_kr_tax_history(), slippage=0.001)
    # 2019년은 첫 entry(2020-01-01) 이전 → 0
    assert em.get_tax_rate(date(2019, 6, 15)) == pytest.approx(0.0)


def test_tax_rate_accepts_typed_entries():
    em = ExecutionModel(
        fee_rate=0.00015,
        tax_rate=[
            TaxRateEntry(from_date=date(2024, 1, 1), rate=0.0018),
            TaxRateEntry(from_date=date(2025, 1, 1), rate=0.0015),
        ],
        slippage=0.001,
    )
    assert em.get_tax_rate(date(2024, 6, 15)) == pytest.approx(0.0018)
    assert em.get_tax_rate(date(2025, 6, 15)) == pytest.approx(0.0015)


def test_tax_rate_unsorted_input_normalized():
    """입력이 from_date 정렬 안 돼 있어도 내부에서 정렬."""
    em = ExecutionModel(
        fee_rate=0.00015,
        tax_rate=[
            {"from": "2025-01-01", "rate": 0.0015},
            {"from": "2024-01-01", "rate": 0.0018},
        ],
        slippage=0.001,
    )
    assert em.get_tax_rate(date(2024, 6, 15)) == pytest.approx(0.0018)
    assert em.get_tax_rate(date(2025, 6, 15)) == pytest.approx(0.0015)


# === 가격 컬럼 선택 ===


def test_get_entry_price_uses_adjusted_by_default():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    row = {"adj_open": 100.0, "open": 200.0, "adj_close": 110.0, "close": 220.0}
    assert em.get_entry_price(row, "open") == 100.0
    assert em.get_entry_price(row, "close") == 110.0


def test_get_entry_price_raw_when_use_adjusted_false():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0, use_adjusted_price=False)
    row = {"open": 200.0, "close": 220.0}
    assert em.get_entry_price(row, "open") == 200.0


def test_get_entry_price_invalid_type_raises():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    with pytest.raises(ValueError):
        em.get_entry_price({"adj_open": 1.0}, "midnight")


# === 슬리피지 + 호가 단위 ===


def test_apply_slippage_buy_uses_round_up():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.001)
    # 100,000원 + 0.1% = 100,100 → 호가 100원 단위라 그대로 100,100
    assert em.apply_slippage_and_tick(100_000, side="buy") == 100_100


def test_apply_slippage_sell_uses_round_down():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.001)
    # 100,000원 - 0.1% = 99,900 → 호가 100원 단위 (50,000~200,000) 그대로
    assert em.apply_slippage_and_tick(100_000, side="sell") == 99_900


def test_apply_slippage_invalid_side_raises():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    with pytest.raises(ValueError):
        em.apply_slippage_and_tick(100_000, side="long")


# === 비용 계산 ===


def test_buy_cost_includes_fee():
    em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0, slippage=0.0)
    res = em.calculate_buy_cost(price=10_000, quantity=10)
    assert isinstance(res, ExecutionResult)
    assert res.side == "buy"
    assert res.gross_amount == pytest.approx(100_000)
    assert res.fee == pytest.approx(100_000 * 0.0015)
    assert res.tax == 0.0  # BUY는 세금 없음
    assert res.net_amount == pytest.approx(100_000 + 100_000 * 0.0015)


def test_sell_proceeds_subtracts_fee_and_tax():
    em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
    res = em.calculate_sell_proceeds(
        price=10_000, quantity=10, on_date=date(2024, 6, 1)
    )
    assert isinstance(res, ExecutionResult)
    assert res.side == "sell"
    gross = 100_000
    assert res.gross_amount == pytest.approx(gross)
    assert res.fee == pytest.approx(gross * 0.0015)
    assert res.tax == pytest.approx(gross * 0.0018)
    assert res.net_amount == pytest.approx(gross - gross * 0.0015 - gross * 0.0018)


def test_sell_proceeds_uses_correct_tax_rate_per_date():
    em = ExecutionModel(fee_rate=0.0, tax_rate=_kr_tax_history(), slippage=0.0)
    # 2024 → 0.0018, 2025 → 0.0015
    r_2024 = em.calculate_sell_proceeds(10_000, 10, date(2024, 6, 1))
    r_2025 = em.calculate_sell_proceeds(10_000, 10, date(2025, 6, 1))
    assert r_2024.tax == pytest.approx(100_000 * 0.0018)
    assert r_2025.tax == pytest.approx(100_000 * 0.0015)
    assert r_2024.net_amount == pytest.approx(100_000 * (1 - 0.0018))
    assert r_2025.net_amount == pytest.approx(100_000 * (1 - 0.0015))


# === 생성자 검증 ===


def test_negative_fee_rate_raises():
    with pytest.raises(ValueError):
        ExecutionModel(fee_rate=-0.001, tax_rate=0.0, slippage=0.0)


def test_negative_slippage_raises():
    with pytest.raises(ValueError):
        ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=-0.001)


# === ExecutionResult dataclass (리뷰 011 H1 + M4) ===


def test_execution_result_buy_invariants():
    """BUY: net = gross + fee, tax = 0, slippage_applied = gross - raw*qty."""
    em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0023, slippage=0.001)
    # raw_price 9990 → slippage 후 약 10000원으로 호가 보정됨
    res = em.calculate_buy_cost(price=10_000, quantity=10, raw_price=9_990)
    assert res.side == "buy"
    assert res.price == 10_000
    assert res.quantity == 10
    assert res.gross_amount == pytest.approx(100_000)
    assert res.fee == pytest.approx(150)
    assert res.tax == 0.0  # BUY는 세금 없음
    assert res.net_amount == pytest.approx(100_150)
    assert res.slippage_applied == pytest.approx(100_000 - 9_990 * 10)


def test_execution_result_sell_invariants():
    """SELL: net = gross - fee - tax, tax는 on_date 기준."""
    em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.001)
    res = em.calculate_sell_proceeds(
        price=10_000, quantity=10, on_date=date(2024, 6, 1), raw_price=10_010
    )
    assert res.side == "sell"
    assert res.gross_amount == pytest.approx(100_000)
    assert res.fee == pytest.approx(150)
    assert res.tax == pytest.approx(180)
    assert res.net_amount == pytest.approx(100_000 - 150 - 180)


def test_execution_result_to_log_dict_keys():
    em = ExecutionModel(fee_rate=0.0015, tax_rate=0.0018, slippage=0.0)
    res = em.calculate_sell_proceeds(price=10_000, quantity=10, on_date=date(2024, 6, 1))
    d = res.to_log_dict()
    assert set(d.keys()) == {
        "price",
        "quantity",
        "gross_amount",
        "fee",
        "tax",
        "net_amount",
        "slippage_applied",
    }


def test_execution_result_zero_quantity_raises():
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    with pytest.raises(ValueError):
        em.calculate_buy_cost(price=10_000, quantity=0)
    with pytest.raises(ValueError):
        em.calculate_sell_proceeds(price=10_000, quantity=0, on_date=date(2024, 1, 1))


def test_execution_result_immutable():
    """frozen dataclass — 외부에서 수정 불가."""
    from dataclasses import FrozenInstanceError

    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    res = em.calculate_buy_cost(price=10_000, quantity=10)
    with pytest.raises(FrozenInstanceError):
        res.price = 99_999  # type: ignore[misc]
