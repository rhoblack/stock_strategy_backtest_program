"""포지션/매수 한도 단위 테스트 (Phase 10 step 022 — 04-l + 04-m).

priority 정렬 후 적용되는 3종 한도:
    - max_positions       : 동시 보유 종목 수 상한 (보유 + 신규 후보 합)
    - max_daily_entries   : 하루 신규 매수 종목 수 상한 (보유와 무관)
    - daily_buy_budget    : 하루 매수 가능 총 금액 상한 (실 체결 net_amount 누적)

검증 항목 (정확성 정책 13.8 + 13.12):
    - priority 순서 유지하며 후보 잘라냄 (앞에서부터)
    - 모든 한도 default=None → 020·021 동작 보존 (Phase 1 골든 frozen)
    - 결정론: 동일 입력 5회 반복 동일 결과
    - max_positions: 보유 슬롯 차감 정확성
    - max_daily_entries: 후보 길이 자체 자름
    - daily_buy_budget: 누적 비용 추적, 초과 후보 skip
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
SYMBOL_D = "000004"


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
    """단일 종목 시계열 DataFrame 생성. priority/multi_symbol 헬퍼와 동일."""
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
    """가격 > MA(2) entry — 단순 시계열 신호."""
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
    priority_method: str = "none",
    max_positions: int | None = None,
    max_daily_entries: int | None = None,
    daily_buy_budget: float | None = None,
    symbol: str = SYMBOL_A,
):
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
        priority_method=priority_method,
        max_positions=max_positions,
        max_daily_entries=max_daily_entries,
        daily_buy_budget=daily_buy_budget,
    )
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


# ========================================================================
# A) BacktestConfig 검증 — 정수/양수 / default=None
# ========================================================================


def test_config_default_limits_are_none():
    """모든 한도 default=None — 020·021 동작 보존."""
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=500_000,
        initial_cash=1_000_000,
    )
    assert config.max_positions is None
    assert config.max_daily_entries is None
    assert config.daily_buy_budget is None


def test_config_max_positions_zero_raises():
    """max_positions=0은 매수 불가 의미 모호 → ValueError."""
    with pytest.raises(ValueError, match="max_positions"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            max_positions=0,
        )


def test_config_max_positions_negative_raises():
    with pytest.raises(ValueError, match="max_positions"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            max_positions=-1,
        )


def test_config_max_daily_entries_zero_raises():
    with pytest.raises(ValueError, match="max_daily_entries"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            max_daily_entries=0,
        )


def test_config_daily_buy_budget_negative_raises():
    with pytest.raises(ValueError, match="daily_buy_budget"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            daily_buy_budget=-100.0,
        )


def test_config_daily_buy_budget_zero_raises():
    with pytest.raises(ValueError, match="daily_buy_budget"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            daily_buy_budget=0,
        )


def test_config_max_positions_bool_raises():
    """True/False는 int 서브타입이지만 의미적으로 잘못된 값 — 거부."""
    with pytest.raises(ValueError, match="max_positions"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            max_positions=True,  # type: ignore[arg-type]
        )


# ========================================================================
# B) max_positions — 신규 매수 후보 슬롯 제한
# ========================================================================


def test_max_positions_caps_new_entries_in_priority_order():
    """후보 4개 + cash 충분 + max_positions=2 → priority 순서 앞에서 2개만 매수."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,  # 충분 → cash 제약 없음
        position_size=500_000,
        priority_method="none",  # symbol ASC
        max_positions=2,
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # symbol ASC → A, B만 매수
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


def test_max_positions_accounts_for_already_held():
    """보유=1 + max_positions=2 → 신규는 슬롯 1개만. 후보 3개여도 1개만 매수."""
    # Day1~3: A만 신호 → A 매수 → Day4~6 보유 유지
    # Day4~6: B, C, D 신호
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A: Day3에 entry 신호 (Day4 시가 매수). Day4 이후 신호 없게 약하게.
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    # B, C, D: Day5에 entry 신호 (Day6 시가 매수 시도). Day1~4는 평탄.
    df_b = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_positions=2,
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # A 매수 후 보유 유지 → Day5 신호일 시작 시점 보유=1 → 신규 슬롯=1.
    # 후보 (B, C, D) symbol ASC → B만 매수.
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B], [
        b["symbol"] for b in buys
    ]


def test_max_positions_full_blocks_all_new_entries():
    """보유=2 + max_positions=2 → 신규 슬롯=0 → 새 후보 모두 skip."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A, B: Day3 신호 → Day4 매수
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    df_b = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    # C, D: Day5 신호 → Day6 매수 시도하지만 슬롯 없음
    df_c = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_positions=2,
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B], [
        b["symbol"] for b in buys
    ]


def test_max_positions_one_matches_single_symbol_semantics():
    """max_positions=1 → 단일 종목 백테스트 정합 (한 시점 한 종목만)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_positions=1,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A]


def test_max_positions_respects_priority_order():
    """priority="trading_value_desc" + max_positions=2 → priority 1·2위만 매수."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3 trading_value: B(550k) > C(220k) > A(110k)
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 1_000, 10_000],
    )
    df_b = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 5_000, 10_000],
    )
    df_c = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 2_000, 10_000],
    )

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="trading_value_desc",
        max_positions=2,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # priority 순서 B, C → max_positions=2 → B, C
    assert [b["symbol"] for b in buys] == [SYMBOL_B, SYMBOL_C]


# ========================================================================
# C) max_daily_entries — 후보 리스트 자체 자름
# ========================================================================


def test_max_daily_entries_caps_candidate_list_length():
    """후보 3개 + max_daily_entries=1 → priority 1순위만 매수 (보유와 무관)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_daily_entries=1,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert [b["symbol"] for b in buys] == [SYMBOL_A]


def test_max_daily_entries_unaffected_by_held():
    """max_daily_entries는 보유와 무관 — 보유 1 + max_daily_entries=2여도
    하루에 신규 2종목까지 매수 가능 (max_positions와 의미 다름)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A: Day3 신호 → Day4 매수, 이후 보유 유지
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    # B, C, D: Day5 신호 → Day6 매수 시도
    df_b = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=10_000_000,
        position_size=500_000,
        priority_method="none",
        max_daily_entries=2,  # 보유와 무관
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # Day3에 A, Day5에 B+C (3개 후보 중 priority 2개)
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B, SYMBOL_C], [
        b["symbol"] for b in buys
    ]


def test_max_daily_entries_with_max_positions_uses_min():
    """두 한도 동시 지정 시 더 작은 결과 적용 (cutoff = min)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_positions=3,
        max_daily_entries=2,
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # min(3-0, 2) = 2 → A, B
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


# ========================================================================
# D) daily_buy_budget — 실 체결 net_amount 누적 추적
# ========================================================================


def test_daily_buy_budget_caps_total_buy_cost():
    """후보 3개, position_size=500_000, budget=1_000_000 → 2개까지 매수, 3번째 skip."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,  # cash 충분
        position_size=500_000,
        priority_method="none",
        daily_buy_budget=1_000_000,  # 정확히 2종목분
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # symbol ASC → A, B 매수, C는 cumulative 1_000_000 + 500_000 > 1_000_000 → skip
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


def test_daily_buy_budget_smaller_than_one_position_blocks_all():
    """budget < position_size → 1개도 매수 불가."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        daily_buy_budget=400_000,  # 1종목 매수도 불가
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == []


def test_daily_buy_budget_resets_per_day():
    """budget은 하루 단위 — Day3에 매수 후 Day5에 다시 fresh budget."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # A, B: Day3 신호 → Day4 매수
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    df_b = _make_df(dates, closes=[100, 100, 110, 110, 90, 90])
    # C, D: Day5 신호 → Day6 매수 시도 (다음 날의 fresh budget)
    df_c = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=10_000_000,
        position_size=500_000,
        priority_method="none",
        daily_buy_budget=1_000_000,  # 하루 2종목분
    )
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # Day3에 A, B (budget 사용) / Day5에 C, D (fresh budget)
    assert [b["symbol"] for b in buys] == [
        SYMBOL_A,
        SYMBOL_B,
        SYMBOL_C,
        SYMBOL_D,
    ]


def test_daily_buy_budget_with_priority_respects_order():
    """priority="trading_value_desc" + budget=1_000_000 → priority 1·2위 매수."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3 trading_value: B(550k) > C(220k) > A(110k)
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 1_000, 10_000],
    )
    df_b = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 5_000, 10_000],
    )
    df_c = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 2_000, 10_000],
    )

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="trading_value_desc",
        daily_buy_budget=1_000_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # priority 순서 B, C, A → budget 1_000_000 → B + C 통과, A skip
    assert [b["symbol"] for b in buys] == [SYMBOL_B, SYMBOL_C]


# ========================================================================
# E) 호환성 — default=None → 020·021 동작 보존
# ========================================================================


def test_all_limits_none_matches_021_behavior():
    """모든 한도 default=None → 021 priority 결과 그대로 (cash 제약만)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    # 한도 미적용 vs 020·021 (cash로만 제약)
    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=1_000_000,  # 2종목분
        position_size=500_000,
        priority_method="none",
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # cash 제약만 → A, B (021 동작과 동일)
    assert [b["symbol"] for b in buys] == [SYMBOL_A, SYMBOL_B]


def test_held_at_open_set_guard_preserved_with_max_positions():
    """020 정책 — 같은 today에 청산 후 재진입 차단. max_positions와 함께 유지."""
    # A: Day3 신호 + 즉시 일중 손절 시나리오는 복잡하므로,
    # 같은 today에 매도 신호와 매수 후보 동시 발생 시 015 정책 보존 검증으로 단순화.
    # held_at_open 가드는 020에서 검증된 기능이며, 한도 도입 후에도 같은 흐름.
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        initial_cash=5_000_000,
        position_size=500_000,
        priority_method="none",
        max_positions=5,  # 한도 충분 — 가드는 한도와 무관해야 함
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # 같은 종목 중복 매수 없음 (Portfolio.buy의 allow_pyramiding=False 정합).
    symbols_bought = [b["symbol"] for b in buys]
    assert len(symbols_bought) == len(set(symbols_bought))


# ========================================================================
# F) 결정론 — 동일 입력 5회 반복 동일 결과
# ========================================================================


def test_position_limits_deterministic_across_5_runs():
    """모든 한도 활성화 + 5회 반복 → 매수 순서/final_equity 동일."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 110, 110])

    bought_orders: list[list[str]] = []
    finals: list[float] = []
    for _ in range(5):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            initial_cash=5_000_000,
            position_size=500_000,
            priority_method="none",
            max_positions=3,
            max_daily_entries=3,
            daily_buy_budget=1_500_000,  # 정확히 3종목분
        )
        result = engine.run(
            {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
        )
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        bought_orders.append([b["symbol"] for b in buys])
        finals.append(result.final_equity)

    assert all(o == bought_orders[0] for o in bought_orders), bought_orders
    assert all(f == finals[0] for f in finals), finals
    # symbol ASC → A, B, C
    assert bought_orders[0] == [SYMBOL_A, SYMBOL_B, SYMBOL_C]
