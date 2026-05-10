"""복수 종목 BacktestEngine 시나리오 테스트 (Phase 10 step 020).

외부 리뷰 CR-003 — BacktestEngine이 dict[symbol, DataFrame] 입력으로 확장.
단일 종목 호환성(자동 wrap) + universe_resolver + symbol ASC 후보 정렬 검증.

본 step에서는 priority 알고리즘 / max_positions / 거래정지 강제 매도는 도입하지
않는다. 후속 step에서 본 모듈에 추가될 시나리오:
    - step 021: priority 알고리즘 (trading_value_desc / market_cap_desc / random)
    - step 022: max_positions / max_daily_entries / daily_buy_budget
    - step 023: event_log / 상장폐지·거래정지 강제 매도
"""

from datetime import date

import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL_A = "000001"
SYMBOL_B = "000002"
SYMBOL_C = "000003"


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
    """단일 종목 시계열 DataFrame 생성. test_backtest_engine.py와 동일한 헬퍼."""
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


def _trivial_entry_strategy() -> dict:
    """가격 > MA(2) entry. 단순 시계열 신호."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }


def _make_engine(
    *,
    strategy: dict,
    initial_cash: float = 2_000_000,
    position_size: float = 500_000,
    symbol: str = SYMBOL_A,
):
    """단일 종목 호환을 위해 config.symbol을 받는다 (다종목 흐름에서는 무시될 수
    있음). prices가 dict로 들어오면 config.symbol은 단순히 fallback으로만 쓰임.
    """
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
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


# ========================================================================
# A) 단일 DataFrame 자동 wrap 호환 (Phase 1 골든 호환의 unit-level 검증)
# ========================================================================


def test_single_dataframe_input_auto_wraps_to_dict():
    """단일 DataFrame 입력 시 자동으로 {config.symbol: df}로 wrap되어
    015 이전과 동일하게 동작 — Phase 1 골든 fixture 호환의 unit-level 검증.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 100, 110, 110])
    engine = _make_engine(strategy=_trivial_entry_strategy(), symbol=SYMBOL_A)
    result = engine.run(df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1
    assert buys[0]["symbol"] == SYMBOL_A


def test_single_symbol_dict_equivalent_to_single_dataframe():
    """{symbol: df}로 명시 전달도 동일 결과."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 100, 110, 110])

    engine_df = _make_engine(strategy=_trivial_entry_strategy(), symbol=SYMBOL_A)
    result_df = engine_df.run(df)

    engine_dict = _make_engine(strategy=_trivial_entry_strategy(), symbol=SYMBOL_A)
    result_dict = engine_dict.run({SYMBOL_A: df})

    assert result_df.final_equity == result_dict.final_equity
    assert len(result_df.trade_executions) == len(result_dict.trade_executions)


# ========================================================================
# B) 복수 종목 동시 매수 — cash 충분
# ========================================================================


def test_two_symbols_simultaneous_entry_both_buy_when_cash_sufficient():
    """2종목이 같은 거래일에 entry True → 둘 다 매수 (cash 충분).

    각 500_000원 매수 + 1_000_000원 충분.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day2(12)에 양 종목 모두 110 → MA(2)=105 → entry True → Day3(15) 매수.
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
        position_size=500_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 2, [b["symbol"] for b in buys]
    assert {b["symbol"] for b in buys} == {SYMBOL_A, SYMBOL_B}
    # 모두 같은 execution_date(=Day3)에 체결
    for b in buys:
        assert b["execution_date"] == date(2024, 1, 15)


def test_existing_position_plus_new_entry_added_for_other_symbol():
    """1종목 보유 중 + 다른 종목에 entry 신호 → 신규 매수 추가."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A: Day2(12) entry True → Day3 매수
    # B: Day3(15) entry True (Day3에 수치를 110으로 만들고 직전이 100) → Day4 매수
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 100, 110, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
        position_size=500_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 2
    by_symbol = {b["symbol"]: b for b in buys}
    assert by_symbol[SYMBOL_A]["execution_date"] == date(2024, 1, 15)
    assert by_symbol[SYMBOL_B]["execution_date"] == date(2024, 1, 16)


# ========================================================================
# C) 후보 정렬 — symbol ASC tie-breaker (priority는 step 021에서 도입)
# ========================================================================


def test_simultaneous_entries_processed_in_symbol_asc_order_when_cash_partial():
    """같은 거래일에 3종목 entry True + cash가 1.5종목분만 충분.

    symbol ASC 순서로 처리되어 SYMBOL_A 먼저, SYMBOL_B 그 다음, SYMBOL_C는
    cash 부족으로 skip되어야 한다 (priority 알고리즘 도입 전 기본 정렬).
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 모두 Day3 매수 시도 (시가 110, 500_000원 / 110 = 4545주, 비용 ≈ 499_950원).
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    # cash 1_000_000 → 2종목까지만 매수 가능 (500_000 × 2 = 1_000_000).
    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,
        position_size=500_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    bought_symbols = [b["symbol"] for b in buys]
    # symbol ASC → A, B 우선 매수, C는 cash 부족으로 skip
    assert bought_symbols == [SYMBOL_A, SYMBOL_B], bought_symbols


def test_cash_shortage_skips_remaining_candidates_but_not_earlier_ones():
    """3종목 entry True + cash가 1종목분만 충분 → SYMBOL_A만 매수, B/C skip."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=600_000,
        position_size=500_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A]


# ========================================================================
# D) universe_resolver — 일별 active universe 동적 변경
# ========================================================================


def test_universe_resolver_excludes_symbol_from_buy_candidates():
    """universe_resolver가 SYMBOL_B를 제외 → A만 매수."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])

    def resolver(_today: date) -> list[str]:
        return [SYMBOL_A]

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b}, universe_resolver=resolver)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A]


def test_universe_resolver_changes_per_day():
    """universe_resolver가 일별로 다른 결과 → 그 날 universe만 매수 후보.

    A는 Day1(11) 신호 → Day2(12) 매수일이 universe에 들어 있을 때만 매수.
    B는 Day3(15) 신호 → Day4(16) 매수일이 universe에 들어 있을 때만 매수.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A: Day1(11)에 110 → MA(2)=100 → entry True → Day2(12) 매수 후보
    df_a = _make_df(dates, closes=[100, 110, 110, 110, 110, 110])
    # B: Day3(15)에 110, Day2(12)는 100 → MA(2)=100 → entry True → Day4(16) 매수 후보
    df_b = _make_df(dates, closes=[100, 100, 100, 110, 110, 110])

    def resolver(today: date) -> list[str]:
        if today == date(2024, 1, 11):
            return [SYMBOL_A]  # A entry 신호일 → Day2(12) 매수
        if today == date(2024, 1, 15):
            return [SYMBOL_B]  # B entry 신호일 → Day4(16) 매수
        # 그 외 날짜는 universe 비움 — 신규 매수 차단
        return []

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b}, universe_resolver=resolver)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    by_symbol_date = {(b["symbol"], b["execution_date"]) for b in buys}
    # A: Day2(12) 매수, B: Day4(16) 매수
    assert (SYMBOL_A, date(2024, 1, 12)) in by_symbol_date, by_symbol_date
    assert (SYMBOL_B, date(2024, 1, 16)) in by_symbol_date, by_symbol_date


def test_universe_resolver_does_not_block_held_position_evaluation():
    """이미 보유 중인 종목이 universe에서 빠져도 매도 평가는 진행.

    설계 §6 Step 2: 보유 종목 가격 업데이트 + 매도 평가는 universe와 독립.
    A를 매수 후 다음 거래일 universe에서 A를 빼도, exit_signal 매도가 정상 발동.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A: Day2(12) 매수 신호 → Day3(15) 매수, Day4(16) 가격 하락 → exit_signal True
    #    → Day5(17) 시가 매도.
    df_a = _make_df(dates, closes=[100, 110, 110, 110, 95, 95])

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        },
        "exit_signal": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": "<"}],
        },
    }

    def resolver(today: date) -> list[str]:
        # Day3 이후 (15부터) A를 universe에서 제외 — 이미 매수 후이므로 신규 진입은
        # 영향 없고, 보유 평가는 universe와 무관하게 진행되어야 한다.
        if today >= date(2024, 1, 15):
            return []
        return [SYMBOL_A]

    engine = _make_engine(
        strategy=strategy,
        initial_cash=2_000_000,
    )
    result = engine.run({SYMBOL_A: df_a}, universe_resolver=resolver)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    sells = [
        ex
        for ex in result.trade_executions
        if "SELL" in ex["execution_type"] and ex["reason"] == "exit_signal"
    ]
    assert len(buys) == 1, buys
    assert len(sells) == 1, sells


# ========================================================================
# E) 결정론 — 복수 종목 시나리오 5회 반복 동일 결과
# ========================================================================


def test_multi_symbol_determinism_5_runs():
    """3종목 + cash 일부 부족 시나리오를 5회 반복 → 모든 결과 동일 (final_equity,
    trade 수, 첫 매수 종목 ASC 순서).
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])

    finals = []
    trade_counts = []
    first_buy_symbols = []

    for _ in range(5):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            initial_cash=1_000_000,
            position_size=500_000,
        )
        result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
        finals.append(result.final_equity)
        trade_counts.append(len(result.trade_executions))
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        if buys:
            first_buy_symbols.append(buys[0]["symbol"])

    assert all(f == finals[0] for f in finals), f"final_equity 불일치: {finals}"
    assert all(c == trade_counts[0] for c in trade_counts), trade_counts
    assert all(s == first_buy_symbols[0] for s in first_buy_symbols), first_buy_symbols
    # symbol ASC tie-breaker로 SYMBOL_A 먼저
    assert first_buy_symbols[0] == SYMBOL_A


# ========================================================================
# F) 입력 정규화 — 잘못된 타입/빈 dict 거부
# ========================================================================


def test_empty_prices_dict_raises():
    """빈 dict 입력 → 명시적 에러."""
    engine = _make_engine(strategy=_trivial_entry_strategy())
    with pytest.raises(ValueError, match="비어"):
        engine.run({})


def test_invalid_prices_value_type_raises():
    """dict의 value가 DataFrame이 아니면 명시적 에러."""
    engine = _make_engine(strategy=_trivial_entry_strategy())
    with pytest.raises(TypeError, match="DataFrame"):
        engine.run({SYMBOL_A: "not a dataframe"})  # type: ignore[arg-type]


def test_invalid_prices_top_type_raises():
    """list 등 잘못된 타입 → 명시적 에러."""
    engine = _make_engine(strategy=_trivial_entry_strategy())
    with pytest.raises(TypeError, match="DataFrame|dict"):
        engine.run([1, 2, 3])  # type: ignore[arg-type]


# ========================================================================
# G) 같은 today에 한 종목 청산 + 다른 종목 신규 매수 동시
# ========================================================================


def test_same_day_exit_a_and_buy_b():
    """A 매도 + B 신규 매수가 같은 today에 동시 발생 — 정상 처리.

    A: Day1(11) entry True → Day2(12) 매수, Day3(15) 일중 익절 (당일 체결).
    B: Day3(15) entry True → Day4(16) 매수.
    같은 Day3(15)에 A 청산 + B 매수 후보 평가가 모두 일어나는지 검증.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # A: Day1(11)에 110 → MA(2)=100 → entry True → Day2(12) 매수 110.
    #    Day3(15) high 130 → 110*1.07=117.7 익절선 도달 → 당일 체결.
    df_a = _make_df(
        dates,
        closes=[100, 110, 110, 125, 125],
        opens=[100, 110, 110, 115, 125],
        highs=[100, 110, 110, 130, 125],
        lows=[100, 110, 110, 113, 120],
    )
    # B: Day3(15)에 entry True가 발생하도록 — Day2(12)=100, Day3(15)=110 → MA(2)=100,
    #    110 > 100 → entry True → Day4(16) 매수.
    df_b = _make_df(dates, closes=[100, 100, 100, 110, 110])

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 7.0, "trigger": "intraday_high"}
            ],
        },
    }

    engine = _make_engine(strategy=strategy, initial_cash=2_000_000, position_size=500_000)
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert {b["symbol"] for b in buys} == {SYMBOL_A, SYMBOL_B}, [b["symbol"] for b in buys]
    assert len(sells) == 1, sells
    assert sells[0]["symbol"] == SYMBOL_A
    assert sells[0]["reason"] == "take_profit"
    assert sells[0]["execution_date"] == date(2024, 1, 15)
    # B의 매수는 Day3 신호 → Day4(16) 체결
    by_sym = {b["symbol"]: b for b in buys}
    assert by_sym[SYMBOL_B]["execution_date"] == date(2024, 1, 16), by_sym[SYMBOL_B]


# ========================================================================
# H) 종목별 거래정지 — 다른 종목은 영향 받지 않음
# ========================================================================


def test_per_symbol_no_volume_skips_only_that_symbol():
    """A는 거래정지(volume=0), B는 정상 → A는 매수/매도 skip되지만 B는 정상.

    015 단일 종목 흐름은 거래정지 시 그날 _record_daily_equity만 했다. 다종목
    흐름에서는 종목별로 skip하고 나머지 종목은 정상 처리.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # A: Day2(12)에 거래정지 (volume=0)
    df_a = _make_df(
        dates,
        closes=[100, 100, 110, 110, 110],
        volumes=[10_000, 10_000, 0, 10_000, 10_000],
    )
    # B: 정상 → Day2 entry True → Day3(15) 매수
    df_b = _make_df(dates, closes=[100, 100, 110, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=2_000_000,
        position_size=500_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # A는 Day2 거래정지로 entry_signal 평가가 스킵 (그날 매수 후보에서 제외)
    # B는 Day3에 정상 매수
    assert {b["symbol"] for b in buys} == {SYMBOL_B}
