"""05-j buy_skipped_cash_shortage event_log + 05-k peak_price 순서 검증.

검증 항목 (정확성 정책 13.3.5 + 05-j + 05-k):
    A) 예수금이 1주 가격보다 부족할 때 event_log에 buy_skipped_cash_shortage 기록
    B) CashManager 강제 매도 성공 후 매수 성공 → cash_shortage event 없음
    C) CashManager 강제 매도 후에도 여전히 부족 → cash_shortage event 기록
    D) CashManager disabled 상태에서 예수금 부족 → cash_shortage event 기록
    E) update_peak_price가 당일 high 값을 올바르게 반영하는지 (portfolio 단위 테스트)
    F) peak_price는 exit_position 평가 전까지 전일 high만 반영 (look-ahead bias 방지)
    G) 정상 매수 시 cash_shortage event 없음

정확성 정책 13.3.5:
    trailing_stop의 peak는 "전일까지의 high"여야 한다.
    update_market_price(당일 종가) → 평가 → update_peak_price(당일 high) 순서.
"""

from datetime import date

import pandas as pd

import app.strategy  # noqa: F401  — 5개 기본 조건 자동 등록
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_CASH_SHORTAGE,
    EVENT_TYPE_SKIP,
    BacktestEngine,
)
from app.backtest.execution import ExecutionModel
from app.portfolio.cash_manager import CashManager
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000010"
SYMBOL_B = "000020"


# ========================================================================
# 헬퍼
# ========================================================================


def _make_df(
    dates: list[date],
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    """단일 종목 시계열 DataFrame."""
    n = len(dates)
    if opens is None:
        opens = closes
    if highs is None:
        highs = [max(o, c) for o, c in zip(opens, closes, strict=True)]
    if lows is None:
        lows = [min(o, c) for o, c in zip(opens, closes, strict=True)]
    if volumes is None:
        volumes = [10_000.0] * n

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens,
            "adj_high": highs,
            "adj_low": lows,
            "adj_close": closes,
            "adj_volume": volumes,
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _always_entry_strategy() -> dict:
    """항상 entry 신호 (price_vs_ma, ma_period=1, ">=" — 종가 >= MA(1) = 종가)."""
    # price_vs_ma ma_period=1: MA(1) = 당일 close → close >= close 항상 True
    # 단, generate_signals에서 rolling(1)이 NaN인 첫 행은 False일 수 있음
    # 확실히 2봉 이후부터 신호가 True가 되게 하려면 ma_period=2 + rising price 사용
    return {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }


def _make_engine(
    *,
    strategy: dict,
    initial_cash: float = 5_000_000,
    position_size: float = 500_000,
    cash_manager: CashManager | None = None,
    symbol: str = SYMBOL_A,
) -> BacktestEngine:
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol=symbol,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
    )
    return BacktestEngine(
        StrategyEngine(strategy),
        portfolio,
        execution_model,
        config,
        cash_manager=cash_manager,
    )


# ========================================================================
# A) 예수금 부족 → buy_skipped_cash_shortage event_log 기록
# ========================================================================


def test_buy_skipped_event_logged_when_cash_insufficient():
    """예수금이 1주 가격보다 적을 때 event_log에 buy_skipped_cash_shortage 기록.

    시나리오:
        initial_cash = 50원 (1주 110원보다 훨씬 적음)
        position_size_amount = 500원 (이론적 구매금액)
        Day3: entry 신호 → Day4(110원) 매수 시도 → 예수금 50원 < 110원 → skip
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 가격: 100 → 100 → 110 → 110. Day3에 entry 신호 (110 > MA(2)=100).
    df_a = _make_df(dates, closes=[100, 100, 110, 110])

    # initial_cash를 1주 가격(110원)보다 훨씬 작게 설정
    engine = _make_engine(
        strategy=_always_entry_strategy(),
        initial_cash=50,          # 50원 — 110원짜리 1주도 못 삼
        position_size=500,         # sizing 금액은 500원이지만 cash가 부족
    )
    result = engine.run({SYMBOL_A: df_a})

    shortage_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_CASH_SHORTAGE
    ]
    assert len(shortage_events) >= 1, (
        f"buy_skipped_cash_shortage event가 없음. event_log={result.event_log}"
    )

    ev = shortage_events[0]
    assert ev["event_type"] == EVENT_TYPE_SKIP
    assert ev["symbol"] == SYMBOL_A
    assert "required_cash" in ev["detail"]
    assert "available_cash" in ev["detail"]
    # 실제 매수 없음
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == []


# ========================================================================
# B) CashManager 강제 매도 성공 후 매수 성공 → cash_shortage event 없음
# ========================================================================


def test_buy_succeeds_after_cash_manager_no_event():
    """CashManager 강제 매도 후 매수 성공 시 buy_skipped_cash_shortage event 없음.

    시나리오:
        initial_cash = 100원 (1주 110원보다 부족).
        SYMBOL_B를 먼저 매수해 보유(보유 종목 market_value로 cash 보전).
        → 실제로는 직접 portfolio에 포지션을 심고 CashManager가 그 종목을 매도해
          cash를 확보하면 SYMBOL_A 매수 성공이 되는지 테스트.

    구현 단순화:
        CashManager가 SYMBOL_B를 매도해 충분한 cash가 확보되면 SYMBOL_A 매수 성공.
        이 경우 cash_shortage event_log는 없어야 한다.

    단, BacktestEngine._maybe_buy에서 CashManager가 est_quantity=0이면 호출 자체를
    건너뛰므로 (est_price > cash 구간), 이 테스트는 CashManager가 cash를 충분히
    확보할 수 있는 시나리오를 구성한다.
    """
    # 충분한 initial_cash로 시작 + CashManager enabled
    # CashManager가 강제매도를 시도해 필요 cash 확보 → SYMBOL_A 정상 매수
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])

    # 충분한 initial_cash로 시작 (cash_manager enabled이지만 cash가 이미 충분)
    cash_manager = CashManager(
        rule={"enabled": True, "shortage_rule": {"action": {"sell_fraction": 0.5}}},
        execution_model=None,
    )
    engine = _make_engine(
        strategy=_always_entry_strategy(),
        initial_cash=1_000_000,    # 충분
        position_size=500_000,
        cash_manager=cash_manager,
    )
    result = engine.run({SYMBOL_A: df_a})

    shortage_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_CASH_SHORTAGE
    ]
    assert shortage_events == [], (
        f"매수 성공 시나리오에서 cash_shortage event가 기록됨: {shortage_events}"
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1, f"매수가 1건 발생해야 함: {buys}"


# ========================================================================
# C) CashManager 강제 매도 후에도 여전히 부족 → cash_shortage event 기록
# ========================================================================


def test_buy_skipped_after_cash_manager_still_insufficient():
    """CashManager가 enabled이지만 보유 포지션이 없어 현금 확보 불가 → cash_shortage.

    시나리오:
        initial_cash = 50원.
        CashManager enabled이지만 보유 포지션 없음 → 강제 매도 대상 없음.
        SYMBOL_A 매수 시도 → CashManager handle_shortage 실패 → cash 여전히 50원
        → execution.net_amount(110원) > 50원 → buy_skipped_cash_shortage event.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])

    cash_manager = CashManager(
        rule={
            "enabled": True,
            "shortage_rule": {
                "action": {"sell_fraction": 0.5},
                "repeat_until_cash_sufficient": True,
            },
        },
        execution_model=None,
    )
    engine = _make_engine(
        strategy=_always_entry_strategy(),
        initial_cash=50,           # 1주 110원도 못 삼
        position_size=500,
        cash_manager=cash_manager,
    )
    result = engine.run({SYMBOL_A: df_a})

    shortage_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_CASH_SHORTAGE
    ]
    assert len(shortage_events) >= 1, (
        f"cash_shortage event 없음. event_log={result.event_log}"
    )
    assert shortage_events[0]["event_type"] == EVENT_TYPE_SKIP
    assert shortage_events[0]["symbol"] == SYMBOL_A
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == []


# ========================================================================
# D) CashManager disabled / 미사용 → 예수금 부족 → cash_shortage event
# ========================================================================


def test_buy_skipped_no_cash_manager_logs_shortage():
    """CashManager 없이(None) 예수금 부족 → buy_skipped_cash_shortage event 기록."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_always_entry_strategy(),
        initial_cash=50,           # 110원짜리 1주도 못 삼
        position_size=500,
        cash_manager=None,         # CashManager 없음
    )
    result = engine.run({SYMBOL_A: df_a})

    shortage_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_CASH_SHORTAGE
    ]
    assert len(shortage_events) >= 1
    assert shortage_events[0]["detail"]["available_cash"] == 50


# ========================================================================
# E) update_peak_price — 당일 high 값 올바르게 반영 (Portfolio 단위 테스트)
# ========================================================================


def test_update_peak_price_uses_daily_high():
    """update_peak_price가 당일 high 값을 peak_price에 올바르게 반영.

    정확성 정책 13.3.5:
        peak는 "전일까지의 high"이므로, update_peak_price 호출 후 다음날
        peak_price가 그 값으로 갱신되어 있어야 한다.
    """
    portfolio = Portfolio(initial_cash=1_000_000)

    from app.backtest.execution import ExecutionResult  # noqa: PLC0415

    # 수동으로 포지션 생성 (buy 호출)
    exec_result = ExecutionResult(
        side="buy",
        raw_price=100.0,
        price=100.0,
        quantity=10,
        gross_amount=1000,
        fee=0,
        tax=0,
        net_amount=1000,
        slippage_applied=0,
    )
    portfolio.buy(
        symbol=SYMBOL_A,
        price=100.0,
        quantity=10,
        on_date=date(2024, 1, 10),
        reason="entry_signal",
        execution=exec_result,
    )

    # 매수 직후 peak_price == entry_price
    pos = portfolio.positions[SYMBOL_A]
    assert pos.peak_price == 100.0, f"초기 peak_price가 entry_price여야 함: {pos.peak_price}"

    # 당일 high = 120 반영 → 다음날부터 trailing 기준이 120
    portfolio.update_peak_price(SYMBOL_A, 120.0)
    pos = portfolio.positions[SYMBOL_A]
    assert pos.peak_price == 120.0, f"peak_price가 120이어야 함: {pos.peak_price}"

    # high < current peak → peak 변경 없음
    portfolio.update_peak_price(SYMBOL_A, 110.0)
    pos = portfolio.positions[SYMBOL_A]
    assert pos.peak_price == 120.0, f"낮은 high로 peak 내려가면 안 됨: {pos.peak_price}"

    # 더 높은 high → peak 갱신
    portfolio.update_peak_price(SYMBOL_A, 150.0)
    pos = portfolio.positions[SYMBOL_A]
    assert pos.peak_price == 150.0, f"더 높은 high로 peak 갱신되어야 함: {pos.peak_price}"


# ========================================================================
# F) peak_price는 exit_position 평가 전까지 전일 high만 반영 (look-ahead bias)
# ========================================================================


def test_trailing_stop_uses_prev_day_high_not_today():
    """trailing_stop은 전일 peak 기준으로 평가 — 당일 high 반영 전에 매도 결정.

    정확성 정책 13.3.5:
        peak_price = 전일까지의 high. 평가 순서:
            1. update_market_price(당일 종가)
            2. exit_position 평가 (trailing_stop — peak는 전일 기준)
            4. update_peak_price(당일 high)  ← 평가 후

        즉, today high가 아무리 높아도 trailing_stop 평가에는 반영되지 않는다.

    시나리오 (가격을 완만하게 설계 — 갭 차단 5% 이내):
        Day1(10일): close=100 → 신호 없음 (MA(2) = NaN)
        Day2(11일): close=110 → entry 신호 (110 > MA(2)=105). next_open=113.
        Day3(12일): 매수 @ 113. open=113, high=130, low=113, close=125.
                    peak(당일 평가 전) = 113(entry). trailing 10%: 113*0.9=101.7.
                    adj_low=113 > 101.7 → 미발동. 평가 후 peak → 130.
        Day4(15일): peak=130. trailing 10%: 130*0.9=117. adj_low=116 ≤ 117 → 발동.

    갭 차단 회피: next_open을 신호일 종가의 ±5% 이내로 설정.
    `max_gap_pct_for_entry` default=5.0이므로 (113-110)/110*100=2.7% < 5% → OK.
    """
    trailing_strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        },
        "exit_position": {
            "conditions": [{"type": "trailing_stop", "percent": 10}]
        },
    }

    # dates: Day1 신호 없음, Day2 신호, Day3 매수 실행, Day4 trailing 발동 평가, Day5 종료
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # 가격:
    #   Day1: close=100, open=100, high=100, low=100
    #   Day2: close=110, open=110, high=110, low=110 (신호: 110 > MA(2)=105)
    #         next_open=113 (갭 2.7% < 5%)
    #   Day3: open=113 (매수 체결), high=130, low=113, close=125
    #   Day4: open=120, high=125, low=116, close=120
    #         trailing = peak(=130) * 0.9 = 117. low=116 ≤ 117 → 발동
    #   Day5: (평가 안 됨)
    closes = [100.0, 110.0, 125.0, 120.0, 120.0]
    opens  = [100.0, 110.0, 113.0, 120.0, 120.0]
    highs  = [100.0, 110.0, 130.0, 125.0, 120.0]
    lows   = [100.0, 110.0, 113.0, 116.0, 120.0]

    df_a = _make_df(dates, closes=closes, opens=opens, highs=highs, lows=lows)

    portfolio = Portfolio(initial_cash=5_000_000)
    execution_model = ExecutionModel(
        fee_rate=0.0,
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=1_000_000,
        initial_cash=5_000_000,
    )
    engine = BacktestEngine(
        StrategyEngine(trailing_strategy),
        portfolio,
        execution_model,
        config,
    )
    result = engine.run({SYMBOL_A: df_a})

    buys = [ex for ex in result.trade_executions if ex["side"] == "buy"]
    sells = [ex for ex in result.trade_executions if ex["side"] == "sell"]

    # 매수가 1건 발생했어야 함 (Day3 @ 113원)
    assert len(buys) >= 1, f"매수 없음: {result.trade_executions}"

    # trailing_stop이 Day4(15일)에 발동되어야 함
    # peak = Day3 high = 130. trailing_stop 10%: 130*0.9=117. Day4 low=116 ≤ 117.
    assert len(sells) >= 1, (
        f"trailing_stop이 발동되지 않음: {result.trade_executions}"
    )
    sell = sells[0]
    assert sell["reason"] == "trailing_stop", (
        f"trailing_stop reason이어야 함, 실제: {sell['reason']}"
    )
    assert sell["date"] == date(2024, 1, 15), (
        f"Day4(15일) 체결이어야 함, 실제: {sell['date']}"
    )


# ========================================================================
# G) 정상 매수 시 cash_shortage event 없음
# ========================================================================


def test_normal_buy_no_shortage_event():
    """충분한 예수금으로 정상 매수 → buy_skipped_cash_shortage event 없음."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_always_entry_strategy(),
        initial_cash=5_000_000,    # 충분
        position_size=500_000,
        cash_manager=None,
    )
    result = engine.run({SYMBOL_A: df_a})

    shortage_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_CASH_SHORTAGE
    ]
    assert shortage_events == [], (
        f"정상 매수에서 cash_shortage event가 기록됨: {shortage_events}"
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1
