"""event_log + 강제 매도 단위 테스트 (Phase 10 step 023 — 04-n + 04-o + 13-p + 13-q).

검증 항목 (정확성 정책 13.4 + 13.12 + 04번 §6/§11):
    A) event_log 구조 — list[dict] 키 명세 (date / symbol / event_type / reason / detail)
    B) 거래정지(volume==0) skip event_log — 보유 평가 / 후보 수집 / 다음날 매수 모두
    C) 상한가 매수 차단 + event_log (skip_limit_up_buy)
    D) 하한가 매도 차단 + event_log (skip_limit_down_sell)
    E) 022 한도 skip event_log (skip_max_positions / skip_max_daily_entries / skip_daily_buy_budget)
    F) 갭 초과 매수 차단 + event_log (skip_max_gap)
    G) 상장폐지 강제 매도 + event_log (force_sell_delisted)
    H) default 정책 정합성 — 일반 시계열은 event_log 비어있음 (Phase 1 골든 영향 없음)
    I) 결정론 — 동일 입력 5회 반복 동일 event_log
    J) is_limit_up / is_limit_down 컬럼 우선 사용 (PriceLoader-friendly)
    K) BacktestConfig 검증 (limit_pct 범위, allow_*_limit_* bool)

본 모듈은 020·021·022 호환성을 명시적으로 검증한다 — 한도 기능 default=None
+ allow_*_limit_*=False default + limit_pct=0.27 default 조합이 Phase 1 골든
fixture(단일 종목, 상한가/하한가/거래정지/상장폐지 시나리오 없음)에 영향을
주지 않는다.
"""

from datetime import date

import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import (
    EVENT_REASON_DAILY_BUY_BUDGET,
    EVENT_REASON_FORCE_SELL_DELISTED,
    EVENT_REASON_LIMIT_DOWN_SELL,
    EVENT_REASON_LIMIT_UP_BUY,
    EVENT_REASON_MAX_DAILY_ENTRIES,
    EVENT_REASON_MAX_GAP,
    EVENT_REASON_MAX_POSITIONS,
    EVENT_REASON_NO_VOLUME,
    EVENT_TYPE_FORCE_SELL,
    EVENT_TYPE_SKIP,
    BacktestEngine,
)
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
    is_limit_up: list[bool] | None = None,
    is_limit_down: list[bool] | None = None,
) -> pd.DataFrame:
    """단일 종목 시계열 DataFrame 생성."""
    n = len(dates)
    if opens is None:
        opens = closes
    if highs is None:
        highs = [max(o, c) for o, c in zip(opens, closes, strict=True)]
    if lows is None:
        lows = [min(o, c) for o, c in zip(opens, closes, strict=True)]
    if volumes is None:
        volumes = [10_000.0] * n

    data = {
        "date": dates,
        "adj_open": opens,
        "adj_high": highs,
        "adj_low": lows,
        "adj_close": closes,
        "adj_volume": volumes,
    }
    if is_limit_up is not None:
        data["is_limit_up"] = is_limit_up
    if is_limit_down is not None:
        data["is_limit_down"] = is_limit_down

    df = pd.DataFrame(data)
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
    allow_buy_limit_up: bool = False,
    allow_sell_limit_down: bool = False,
    limit_pct: float = 0.27,
    max_gap_pct_for_entry: float = 5.0,
    symbol: str = SYMBOL_A,
    skip_no_volume: bool = True,
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
        allow_buy_limit_up=allow_buy_limit_up,
        allow_sell_limit_down=allow_sell_limit_down,
        limit_pct=limit_pct,
        max_gap_pct_for_entry=max_gap_pct_for_entry,
        skip_no_volume=skip_no_volume,
    )
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


# ========================================================================
# A) BacktestConfig 검증
# ========================================================================


def test_config_default_limit_policy():
    """default — 보수: 상한가/하한가 차단 + limit_pct=0.27."""
    config = BacktestConfig(
        symbol=SYMBOL_A,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        position_size_amount=500_000,
        initial_cash=1_000_000,
    )
    assert config.allow_buy_limit_up is False
    assert config.allow_sell_limit_down is False
    assert config.limit_pct == 0.27


def test_config_limit_pct_zero_raises():
    with pytest.raises(ValueError, match="limit_pct"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            limit_pct=0,
        )


def test_config_limit_pct_one_raises():
    with pytest.raises(ValueError, match="limit_pct"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            limit_pct=1.0,
        )


def test_config_allow_buy_limit_up_int_raises():
    with pytest.raises(ValueError, match="allow_buy_limit_up"):
        BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            allow_buy_limit_up=1,  # type: ignore[arg-type]
        )


# ========================================================================
# B) event_log 구조 — list[dict] 키 명세
# ========================================================================


def test_event_log_default_initialized_empty():
    """엔진 생성 직후 event_log = []."""
    engine = _make_engine(strategy=_trivial_entry_strategy())
    assert engine.event_log == []


def test_event_log_no_skip_scenario_remains_empty():
    """일반 시계열 (상한가/하한가/거래정지/한도 없음) → event_log 비어있음."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})
    assert result.event_log == []
    assert engine.event_log == []


def test_event_log_entry_keys():
    """각 event는 date / symbol / event_type / reason / detail 키 보유."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        max_positions=1,  # B가 잘림
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})
    assert len(result.event_log) >= 1
    for ev in result.event_log:
        assert set(ev.keys()) == {"date", "symbol", "event_type", "reason", "detail"}
        assert ev["event_type"] in {EVENT_TYPE_SKIP, EVENT_TYPE_FORCE_SELL}
        assert isinstance(ev["detail"], dict)


# ========================================================================
# C) 거래정지(volume==0) event_log
# ========================================================================


def test_event_log_no_volume_in_entry_candidate():
    """후보 수집 단계 — final_entry_signal=True인 봉이 volume==0이면 skip + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3: 신호 (close=110 > MA(2)=100), volume=0
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 0, 10_000],
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})

    no_volume_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_NO_VOLUME
    ]
    assert len(no_volume_events) == 1
    assert no_volume_events[0]["symbol"] == SYMBOL_A
    assert no_volume_events[0]["date"] == date(2024, 1, 12)
    assert no_volume_events[0]["detail"]["phase"] == "entry_candidate"


def test_event_log_no_volume_during_held_evaluation():
    """보유 종목의 today volume==0이면 매도 평가 skip + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # Day3 신호 → Day4 매수 후 보유. Day5 volume=0.
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110, 110],
        volumes=[10_000, 10_000, 10_000, 10_000, 0],
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})

    exit_eval_events = [
        e for e in result.event_log
        if e["reason"] == EVENT_REASON_NO_VOLUME
        and e["detail"].get("phase") == "exit_evaluation"
    ]
    assert len(exit_eval_events) == 1
    assert exit_eval_events[0]["symbol"] == SYMBOL_A
    assert exit_eval_events[0]["date"] == date(2024, 1, 16)


def test_event_log_no_volume_next_day_blocks_buy():
    """next_volume==0이면 다음날 매수 체결 불가 → skip + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3 신호, Day4 next_volume=0 → 매수 skip
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        volumes=[10_000, 10_000, 10_000, 0],
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})

    next_day_events = [
        e for e in result.event_log
        if e["reason"] == EVENT_REASON_NO_VOLUME
        and e["detail"].get("phase") == "next_day_entry"
    ]
    assert len(next_day_events) == 1
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == []


# ========================================================================
# D) 상한가 매수 차단 (skip_limit_up_buy)
# ========================================================================


def test_event_log_limit_up_blocks_buy_via_column():
    """is_limit_up=True 컬럼이 있는 신호일 → 매수 차단 + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        is_limit_up=[False, False, True, False],  # Day3 상한가
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})

    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_UP_BUY
    ]
    assert len(limit_events) == 1
    assert limit_events[0]["symbol"] == SYMBOL_A
    assert limit_events[0]["date"] == date(2024, 1, 12)
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == []


def test_event_log_limit_up_fallback_high_eq_low_and_pct():
    """is_limit_up 컬럼 없고 high==low + 30%↑ 상승 → fallback 판정."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3: 100 → 130 (+30%), high==low==130 (단일가 거래)
    df_a = _make_df(
        dates,
        closes=[100, 100, 130, 130],
        opens=[100, 100, 130, 130],
        highs=[100, 100, 130, 130],
        lows=[100, 100, 130, 130],
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})

    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_UP_BUY
    ]
    assert len(limit_events) == 1


def test_event_log_limit_up_allows_buy_when_opted_in():
    """allow_buy_limit_up=True → 상한가에서도 매수 시도, event_log 기록 X."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110],
        is_limit_up=[False, False, True, False],
    )
    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        allow_buy_limit_up=True,
    )
    result = engine.run({SYMBOL_A: df_a})
    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_UP_BUY
    ]
    assert limit_events == []
    # 매수 시도됨 (Day4 매수)
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1


# ========================================================================
# E) 하한가 매도 차단 (skip_limit_down_sell)
# ========================================================================


def test_event_log_limit_down_blocks_exit_signal_sell():
    """exit_signal=True인 봉이 하한가 → 매도 보류 + log."""
    # exit_signal 전략: price_vs_ma "<".
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
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # Day3: entry 신호 → Day4 매수.
    # Day5: close < MA → exit_signal True. is_limit_down=True → 매도 보류.
    # Day6: 마지막 봉 (next_open NaN) — exit_signal 평가 가능하려면 Day5 다음에 봉 필요.
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110, 80, 90],
        is_limit_down=[False, False, False, False, True, False],
    )
    engine = _make_engine(strategy=strategy)
    result = engine.run({SYMBOL_A: df_a})

    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_DOWN_SELL
    ]
    assert len(limit_events) == 1
    assert limit_events[0]["date"] == date(2024, 1, 16)


def test_event_log_limit_down_allows_sell_when_opted_in():
    """allow_sell_limit_down=True → 하한가 매도 시도."""
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
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    df_a = _make_df(
        dates, closes=[100, 100, 110, 110, 80, 90],
        is_limit_down=[False, False, False, False, True, False],
    )
    engine = _make_engine(strategy=strategy, allow_sell_limit_down=True)
    result = engine.run({SYMBOL_A: df_a})
    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_DOWN_SELL
    ]
    assert limit_events == []


# ========================================================================
# F) 022 한도 skip event_log
# ========================================================================


def test_event_log_max_positions_skip():
    """max_positions=2 + 후보 4 → 2개 잘리며 event_log 기록."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(strategy=_trivial_entry_strategy(), max_positions=2)
    result = engine.run(
        {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
    )
    skip_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_MAX_POSITIONS
    ]
    assert len(skip_events) == 2
    # 잘린 후보는 priority 순서 뒤쪽 (C, D — symbol ASC).
    assert sorted(e["symbol"] for e in skip_events) == [SYMBOL_C, SYMBOL_D]
    for e in skip_events:
        assert e["detail"]["max_positions"] == 2
        assert e["detail"]["available_slots"] == 2


def test_event_log_max_daily_entries_skip():
    """max_daily_entries=1 + 후보 3 → 2개 잘리며 event_log 기록."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(strategy=_trivial_entry_strategy(), max_daily_entries=1)
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    skip_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_MAX_DAILY_ENTRIES
    ]
    assert len(skip_events) == 2
    assert sorted(e["symbol"] for e in skip_events) == [SYMBOL_B, SYMBOL_C]


def test_event_log_daily_buy_budget_skip():
    """budget=1_000_000, position_size=500_000 → 3번째 후보부터 skip + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])

    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        position_size=500_000,
        daily_buy_budget=1_000_000,
    )
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
    skip_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_DAILY_BUY_BUDGET
    ]
    # C가 누적 초과로 skip
    assert len(skip_events) == 1
    assert skip_events[0]["symbol"] == SYMBOL_C
    assert skip_events[0]["detail"]["daily_buy_budget"] == 1_000_000


# ========================================================================
# G) 갭 초과 매수 차단 (skip_max_gap)
# ========================================================================


def test_event_log_max_gap_skip():
    """next_open이 prev close 대비 큰 갭 상승 → 매수 skip + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day3 신호 (close=110 > MA(2)). Day4 시가 = 130 → 갭 +18.18%.
    df_a = _make_df(
        dates,
        closes=[100, 100, 110, 110],
        opens=[100, 100, 110, 130],  # Day4 open=130
    )
    engine = _make_engine(
        strategy=_trivial_entry_strategy(),
        max_gap_pct_for_entry=5.0,
    )
    result = engine.run({SYMBOL_A: df_a})
    gap_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_MAX_GAP
    ]
    assert len(gap_events) == 1
    assert gap_events[0]["symbol"] == SYMBOL_A
    assert gap_events[0]["detail"]["max_gap_pct_for_entry"] == 5.0
    # gap_pct 검증 (130 vs 110 → ~18.18%)
    assert gap_events[0]["detail"]["gap_pct"] > 18


# ========================================================================
# H) 상장폐지 강제 매도 (force_sell_delisted)
# ========================================================================


def test_event_log_force_sell_delisted_at_today():
    """today == delisting_date인 보유 종목 → 강제 매도 + log."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    # Day3 신호 → Day4 매수. Day5가 폐지일.
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110, 110])
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run(
        {SYMBOL_A: df_a},
        delisting_dates={SYMBOL_A: date(2024, 1, 16)},
    )
    force_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_FORCE_SELL_DELISTED
    ]
    assert len(force_events) == 1
    assert force_events[0]["symbol"] == SYMBOL_A
    assert force_events[0]["date"] == date(2024, 1, 16)
    assert force_events[0]["event_type"] == EVENT_TYPE_FORCE_SELL
    assert force_events[0]["detail"]["row_present"] is True
    # 실제 매도 발생
    sells = [ex for ex in result.trade_executions if ex["execution_type"] == "SELL"]
    assert len(sells) == 1
    assert sells[0]["reason"] == EVENT_REASON_FORCE_SELL_DELISTED


def test_event_log_force_sell_delisted_uses_adj_close():
    """강제 매도 가격 = today adj_close."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 105])
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run(
        {SYMBOL_A: df_a},
        delisting_dates={SYMBOL_A: date(2024, 1, 16)},
    )
    force_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_FORCE_SELL_DELISTED
    ]
    assert force_events[0]["detail"]["exit_price"] == 105.0


def test_event_log_force_sell_no_delisting_no_action():
    """delisting_dates=None이면 강제 매도 없음."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110, 110])
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a}, delisting_dates=None)
    force_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_FORCE_SELL_DELISTED
    ]
    assert force_events == []


# ========================================================================
# I) 결정론 — 동일 입력 5회 반복 동일 event_log
# ========================================================================


def test_event_log_deterministic_across_5_runs():
    """모든 skip 시나리오 + 5회 반복 → event_log 동일."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df_a = _make_df(dates, closes=[100, 100, 110, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 110])
    df_c = _make_df(dates, closes=[100, 100, 110, 110])
    df_d = _make_df(dates, closes=[100, 100, 110, 110])

    snapshots: list[list[tuple]] = []
    for _ in range(5):
        engine = _make_engine(
            strategy=_trivial_entry_strategy(),
            max_positions=2,
            daily_buy_budget=1_500_000,
        )
        result = engine.run(
            {SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c, SYMBOL_D: df_d}
        )
        # event_log를 비교 가능한 tuple로 정규화 (date / symbol / reason 만 비교).
        snapshot = [
            (e["date"], e["symbol"], e["event_type"], e["reason"])
            for e in result.event_log
        ]
        snapshots.append(snapshot)
    assert all(s == snapshots[0] for s in snapshots), snapshots


def test_event_log_ordering_date_asc():
    """event_log는 발생 순서(date ASC) 유지."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17, 18, 19)]
    # Day3 신호 (A, B 둘다 후보, max_positions=1 → B 잘림).
    # Day8 또 신호.
    df_a = _make_df(dates, closes=[100, 100, 110, 90, 90, 90, 100, 110])
    df_b = _make_df(dates, closes=[100, 100, 110, 90, 90, 90, 100, 110])

    engine = _make_engine(strategy=_trivial_entry_strategy(), max_positions=1)
    result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b})

    skip_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_MAX_POSITIONS
    ]
    assert len(skip_events) >= 1
    # date가 단조 비감소
    dates_in_log = [e["date"] for e in result.event_log]
    assert dates_in_log == sorted(dates_in_log), dates_in_log


# ========================================================================
# J) is_limit_up / is_limit_down 컬럼 우선
# ========================================================================


def test_limit_up_column_overrides_fallback():
    """is_limit_up=False 명시면 fallback 조건(high==low + pct) 무관하게 매수 시도."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # high==low==130, +30% 상승 — fallback이라면 limit_up. 컬럼 False로 override.
    df_a = _make_df(
        dates,
        closes=[100, 100, 130, 130],
        opens=[100, 100, 130, 130],
        highs=[100, 100, 130, 130],
        lows=[100, 100, 130, 130],
        is_limit_up=[False, False, False, False],
    )
    engine = _make_engine(strategy=_trivial_entry_strategy())
    result = engine.run({SYMBOL_A: df_a})
    limit_events = [
        e for e in result.event_log if e["reason"] == EVENT_REASON_LIMIT_UP_BUY
    ]
    assert limit_events == []
