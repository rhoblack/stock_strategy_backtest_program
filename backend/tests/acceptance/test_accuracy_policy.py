"""13.17 정확성 정책 acceptance 1:1 매핑 파일.

설계서 13번 §17의 11개 항목을 각각 test_13_17_N_* 함수에 1:1 매핑합니다.
각 함수는 해당 항목을 직접 검증하거나, 다른 테스트 파일에서 이미 검증되는 경우
그 의미를 명시한 import-free 리다이렉션 assertion으로 문서화합니다.

§17 항목 목록 (13번 문서 §17):
  1. 일중 손절 도달 정확성
  2. 일중 익절 도달 정확성
  3. 동일 봉 익절·손절 동시 도달 시 손절 우선
  4. 갭 다운 손절 시 시가 체결
  5. 거래정지 종목 매수/매도 차단
  6. 상한가 매수 차단
  7. 호가 단위 반올림
  8. 거래세 시계열 적용
  9. 수정주가 사용 일관성
 10. 동시 신호 우선순위 결정론
 11. random_seed 동일 시 동일 결과

커버 파일 약어:
  BE  = tests/backtest/test_backtest_engine.py
  TICK = tests/backtest/test_tick.py
  EXEC = tests/backtest/test_execution.py
  PRI  = tests/backtest/test_priority.py
  G01  = tests/integration/test_phase1_golden.py
"""

from datetime import date

import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.tick import round_to_tick
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

# ============================================================================
# 공통 헬퍼
# ============================================================================


def _make_df(
    dates: list[date],
    closes: list[float],
    *,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
):
    import pandas as pd

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


def _make_engine(
    strategy: dict,
    *,
    initial_cash: float = 1_000_000,
    position_size: float = 500_000,
    fee_rate: float = 0.0,
    tax_rate: float = 0.0,
    slippage: float = 0.0,
):
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=fee_rate,
        tax_rate=tax_rate,
        slippage=slippage,
        tick_rounding="nearest",
    )
    config = BacktestConfig(
        symbol="005930",
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
    )
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


def _entry_strategy(
    *,
    take_profit: float | None = None,
    stop_loss: float | None = None,
) -> dict:
    """가격 > MA(2) entry, 옵션으로 exit_position 추가."""
    exit_position_conds = []
    if take_profit is not None:
        exit_position_conds.append(
            {"type": "take_profit", "percent": take_profit, "trigger": "intraday_high"}
        )
    if stop_loss is not None:
        exit_position_conds.append({"type": "stop_loss", "percent": stop_loss})
    strategy: dict = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }
    if exit_position_conds:
        strategy["exit_position"] = {"logic": "OR", "conditions": exit_position_conds}
    return strategy


# ============================================================================
# §17.1 — 일중 손절 도달 정확성
# 관련 커버 파일: BE::test_intraday_stop_loss_executes_at_stop_price
#                G01::test_golden_01_ma_cross_take_profit_stop_loss (stop_loss=3%)
# ============================================================================


def test_13_17_1_intraday_stop_loss_at_stop_price():
    """§17.1 — 일중 low가 손절선에 도달하면 손절선 가격에 정확히 체결.

    매수가 110, 손절선 = 110 * (1 - 0.03) = 106.7.
    당일 low 100 ≤ 106.7 → 손절 체결가 106.7.
    시가(108)는 손절선(106.7) 위 → 갭다운 아님.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 105],
        opens=[100, 110, 110, 108],
        highs=[100, 110, 110, 109],
        lows=[100, 110, 110, 100],
    )
    engine = _make_engine(_entry_strategy(stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1, f"손절 체결이 1건이어야 함: {sells}"
    assert sells[0]["price"] == pytest.approx(106.7, abs=0.5), (
        f"손절 체결가 불일치: {sells[0]['price']} (expected ~106.7)"
    )
    assert sells[0]["reason"] == "stop_loss"


# ============================================================================
# §17.2 — 일중 익절 도달 정확성
# 관련 커버 파일: BE::test_intraday_take_profit_executes_at_target
#                G01::test_golden_01_ma_cross_take_profit_stop_loss (take_profit=5%)
# ============================================================================


def test_13_17_2_intraday_take_profit_at_target_price():
    """§17.2 — 일중 high가 익절선에 도달하면 익절선 가격에 정확히 체결.

    매수가 110, 익절선 = 110 * 1.07 = 117.7.
    시가 115 (< 117.7, 갭업 아님), 당일 high 130 ≥ 117.7 → 익절 체결가 117.7.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 125],
        opens=[100, 110, 110, 115],
        highs=[100, 110, 110, 130],
        lows=[100, 110, 110, 113],
    )
    engine = _make_engine(_entry_strategy(take_profit=7.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1, f"익절 체결이 1건이어야 함: {sells}"
    assert sells[0]["price"] == pytest.approx(117.7, abs=0.5), (
        f"익절 체결가 불일치: {sells[0]['price']} (expected ~117.7)"
    )
    assert sells[0]["reason"] == "take_profit"


# ============================================================================
# §17.3 — 동일 봉 익절·손절 동시 도달 시 손절 우선
# 관련 커버 파일: BE::test_simultaneous_take_profit_and_stop_loss_prefers_stop_loss
#                BE::test_exit_position_priority_stop_before_take_via_registry
# ============================================================================


def test_13_17_3_simultaneous_take_and_stop_stop_takes_priority():
    """§17.3 — 같은 봉에서 high ≥ 익절선, low ≤ 손절선 동시 달성 시 손절 우선.

    보수적 정책: 일봉 데이터로 시계열 순서 불명 → 손절(불리한 쪽) 우선.
    매수가 110, take=7% → 117.7, stop=3% → 106.7.
    Day3: high 120 (≥ 117.7), low 100 (≤ 106.7) → 손절 우선.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110],
        opens=[100, 110, 110, 110],
        highs=[100, 110, 110, 120],
        lows=[100, 110, 110, 100],
    )
    engine = _make_engine(_entry_strategy(take_profit=7.0, stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1, f"체결이 1건이어야 함: {sells}"
    assert sells[0]["reason"] == "stop_loss", (
        f"손절 우선이어야 하지만 reason={sells[0]['reason']}"
    )


# ============================================================================
# §17.4 — 갭 다운 손절 시 시가 체결
# 관련 커버 파일: BE::test_gap_down_stop_loss_executes_at_open_price
# ============================================================================


def test_13_17_4_gap_down_stop_loss_executes_at_open():
    """§17.4 — 시가가 이미 손절선 아래이면 (갭 다운) 시가에 체결.

    매수가 110, 손절선 = 110 * 0.97 = 106.7.
    Day3 시가 100 < 106.7 → 100에 체결 (손절선이 아님).
    exit_reason = 'gap_down_stop_loss'.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 102],
        opens=[100, 110, 110, 100],
        highs=[100, 110, 110, 105],
        lows=[100, 110, 110, 95],
    )
    engine = _make_engine(_entry_strategy(stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1, f"갭다운 손절이 1건이어야 함: {sells}"
    assert sells[0]["price"] == pytest.approx(100, abs=0.5), (
        f"갭다운 체결가는 시가(100)이어야 함: {sells[0]['price']}"
    )
    assert sells[0]["reason"] == "gap_down_stop_loss", (
        f"reason 불일치: {sells[0]['reason']}"
    )


# ============================================================================
# §17.5 — 거래정지 종목 매수/매도 차단
# 관련 커버 파일: BE::test_no_volume_skips_processing
# ============================================================================


def test_13_17_5_zero_volume_day_skips_entry():
    """§17.5 — 거래량 0인 날은 매수 신호가 있어도 체결하지 않음.

    entry 신호 발생 → 다음날 시가 체결 예정이나 다음날 volume=0 → skip.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # Day1에 entry True (110 > MA), Day2 next_volume=0 → 매수 skip
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110, 110],
        volumes=[10_000, 10_000, 0, 10_000, 10_000],
    )
    # 강제로 next_volume을 volume 기준으로 재구성 (shift(-1))
    import pandas as pd
    vol = [10_000, 10_000, 0, 10_000, 10_000]
    df_custom = pd.DataFrame(
        {
            "date": dates,
            "adj_open": [100, 110, 110, 110, 110],
            "adj_high": [100, 110, 110, 110, 110],
            "adj_low": [100, 110, 110, 110, 110],
            "adj_close": [100, 110, 110, 110, 110],
            "adj_volume": vol,
        }
    )
    df_custom["next_open"] = df_custom["adj_open"].shift(-1)
    df_custom["next_volume"] = df_custom["adj_volume"].shift(-1)  # Day1 next_volume = 0

    engine = _make_engine(_entry_strategy())
    result = engine.run(df_custom)

    # Day1 entry True이지만 Day2 next_volume=0 → 매수 차단
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # Day2 volume=0이므로 Day1 신호 Day2 체결이 차단되어야 함
    buy_dates = [b["date"] for b in buys]
    # date(2024, 1, 12) (Day2)에 체결된 매수가 없어야 함
    assert date(2024, 1, 12) not in buy_dates, (
        f"거래정지일(vol=0)에 매수가 발생: {buys}"
    )


def test_13_17_5_zero_volume_day_event_log_recorded():
    """§17.5 보완 — 거래량 0인 날 event_log에 skip 이벤트 기록.

    BacktestResult.event_log에 reason='skip_no_volume' 이벤트가 남아야 함.
    (엔진이 event_log를 지원하지 않으면 xfail로 표시)
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    import pandas as pd

    df_custom = pd.DataFrame(
        {
            "date": dates,
            "adj_open": [100, 110, 110, 110],
            "adj_high": [100, 110, 110, 110],
            "adj_low": [100, 110, 110, 110],
            "adj_close": [100, 110, 110, 110],
            "adj_volume": [10_000, 10_000, 0, 10_000],
        }
    )
    df_custom["next_open"] = df_custom["adj_open"].shift(-1)
    df_custom["next_volume"] = df_custom["adj_volume"].shift(-1)

    engine = _make_engine(_entry_strategy())
    result = engine.run(df_custom)

    if not hasattr(result, "event_log"):
        pytest.xfail("BacktestResult에 event_log 속성 미구현 — 향후 확장 예정")

    # 엔진은 reason='skip_no_volume' (혹은 'no_volume')으로 기록
    skip_events = [
        e for e in result.event_log
        if "no_volume" in str(e.get("reason", "")) or "no_volume" in str(e.get("event", ""))
    ]
    assert len(skip_events) >= 1, (
        f"거래량 0 skip 이벤트가 event_log에 기록되어야 함. event_log={result.event_log}"
    )


# ============================================================================
# §17.6 — 상한가 매수 차단
# 관련 커버 파일: BE (상한가 매수 차단 테스트 아직 없음)
# ============================================================================


def test_13_17_6_limit_up_buy_blocked():
    """§17.6 — allow_buy_limit_up=False(기본) 시 상한가 매수 차단.

    BacktestConfig에 allow_buy_limit_up 옵션이 아직 구현되지 않은 경우 xfail.
    신호일 종가가 상한가(+30%)이면 다음날 매수 skip.
    """
    if not hasattr(BacktestConfig, "allow_buy_limit_up"):
        pytest.xfail(
            "BacktestConfig.allow_buy_limit_up 미구현 "
            "(정확성 정책 §4.3 — 향후 구현 필요)"
        )

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day1 close가 상한가 상태 (+30% 이면 상한가 가정)
    df = _make_df(
        dates,
        closes=[100, 130, 130, 130],  # Day1 close = 130 (상한가 가정)
    )
    config = BacktestConfig(
        symbol="005930",
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=500_000,
        initial_cash=1_000_000,
        allow_buy_limit_up=False,
    )
    portfolio = Portfolio(initial_cash=1_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    engine = BacktestEngine(
        StrategyEngine(_entry_strategy()), portfolio, execution_model, config
    )
    result = engine.run(df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 0, f"상한가 매수가 차단되어야 함: {buys}"


# ============================================================================
# §17.7 — 호가 단위 반올림
# 관련 커버 파일: TICK::test_tick_size_thresholds
#                TICK::test_round_nearest_unit_* / test_round_buy_up_*
#                EXEC::test_apply_slippage_buy_uses_round_up
# ============================================================================


def test_13_17_7_tick_rounding_applied_to_execution():
    """§17.7 — 체결가는 호가 단위로 반올림됨.

    slippage 적용 후 정확한 호가 단위 체결가 검증.
    100,000원 + 0.1% slippage = 100,100 → 호가 100원 단위로 100,100 (정합).
    """
    # 직접 round_to_tick 함수 검증
    # 가격대별 호가 단위 정확성 (§5.1)
    assert round_to_tick(1_234, mode="nearest") == 1_234  # < 2,000 → 1원
    assert round_to_tick(25_120, mode="nearest") == 25_100  # 20k~50k → 50원
    assert round_to_tick(75_350, mode="nearest") == 75_400  # 50k~200k → 100원
    assert round_to_tick(250_750, mode="nearest") == 251_000  # 200k~500k → 500원
    assert round_to_tick(750_500, mode="nearest") == 750_000  # ≥ 500k → 1,000원

    # 매수는 위로, 매도는 아래로 (buy_up_sell_down 모드)
    assert round_to_tick(75_310, side="buy", mode="buy_up_sell_down") == 75_400
    assert round_to_tick(75_390, side="sell", mode="buy_up_sell_down") == 75_300


def test_13_17_7_execution_model_applies_slippage_and_tick():
    """§17.7 보완 — ExecutionModel.apply_slippage_and_tick 정합성.

    slippage=0.1% 매수: 100,000 → 100,100 → 호가 100원 단위 100,100.
    """
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.001)
    result_buy = em.apply_slippage_and_tick(100_000, side="buy")
    assert result_buy == 100_100  # 100,000 × 1.001 = 100,100

    result_sell = em.apply_slippage_and_tick(100_000, side="sell")
    assert result_sell == 99_900  # 100,000 × 0.999 = 99,900


# ============================================================================
# §17.8 — 거래세 시계열 적용
# 관련 커버 파일: EXEC::test_tax_rate_timeseries_each_period
#                EXEC::test_sell_proceeds_uses_correct_tax_rate_per_date
#                G01::test_golden_04_with_realistic_costs
# ============================================================================


def test_13_17_8_tax_rate_timeseries_each_period():
    """§17.8 — 거래세가 거래일에 따라 시계열로 올바르게 적용됨.

    한국 거래세 변동 이력 (정확성 정책 §6.1):
      ~2022-12-31: 0.23%
      2023-01-01~: 0.20%
      2024-01-01~: 0.18%
      2025-01-01~: 0.15%
    """
    tax_history = [
        {"from": "2020-01-01", "rate": 0.0023},
        {"from": "2023-01-01", "rate": 0.0020},
        {"from": "2024-01-01", "rate": 0.0018},
        {"from": "2025-01-01", "rate": 0.0015},
    ]
    em = ExecutionModel(fee_rate=0.0, tax_rate=tax_history, slippage=0.0)

    # 각 구간별 정확한 세율
    assert em.get_tax_rate(date(2022, 12, 31)) == pytest.approx(0.0023)
    assert em.get_tax_rate(date(2023, 6, 15)) == pytest.approx(0.0020)
    assert em.get_tax_rate(date(2024, 6, 15)) == pytest.approx(0.0018)
    assert em.get_tax_rate(date(2025, 6, 15)) == pytest.approx(0.0015)


def test_13_17_8_tax_applied_correctly_to_sell_proceeds():
    """§17.8 보완 — 매도 체결 시 해당 거래일 세율이 실제 비용에 정확히 반영.

    2024-06-15 거래: gross 100,000 × 0.0018 = 180원 세금.
    2025-06-15 거래: gross 100,000 × 0.0015 = 150원 세금.
    """
    tax_history = [
        {"from": "2020-01-01", "rate": 0.0023},
        {"from": "2023-01-01", "rate": 0.0020},
        {"from": "2024-01-01", "rate": 0.0018},
        {"from": "2025-01-01", "rate": 0.0015},
    ]
    em = ExecutionModel(fee_rate=0.0, tax_rate=tax_history, slippage=0.0)

    r_2024 = em.calculate_sell_proceeds(10_000, 10, date(2024, 6, 15))
    r_2025 = em.calculate_sell_proceeds(10_000, 10, date(2025, 6, 15))

    assert r_2024.tax == pytest.approx(100_000 * 0.0018)
    assert r_2025.tax == pytest.approx(100_000 * 0.0015)
    # net_amount는 gross - fee - tax
    assert r_2024.net_amount == pytest.approx(100_000 * (1 - 0.0018))
    assert r_2025.net_amount == pytest.approx(100_000 * (1 - 0.0015))


# ============================================================================
# §17.9 — 수정주가 사용 일관성
# 관련 커버 파일: EXEC::test_get_entry_price_uses_adjusted_by_default
# ============================================================================


def test_13_17_9_adjusted_price_used_by_default():
    """§17.9 — use_adjusted_price=True(기본) 시 adj_* 컬럼 사용.

    원 가격과 수정 가격이 다를 때, ExecutionModel이 adj_open을 사용해야 함.
    """
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    # adj_open=100, open=200 → use_adjusted_price=True(기본) → 100 사용
    row = {"adj_open": 100.0, "open": 200.0, "adj_close": 110.0, "close": 220.0}
    assert em.get_entry_price(row, "open") == 100.0, (
        "수정 가격(adj_open)이 사용되어야 함"
    )
    assert em.get_entry_price(row, "close") == 110.0, (
        "수정 종가(adj_close)가 사용되어야 함"
    )


def test_13_17_9_raw_price_when_use_adjusted_false():
    """§17.9 보완 — use_adjusted_price=False이면 원 가격 사용."""
    em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0, use_adjusted_price=False)
    row = {"open": 200.0, "close": 220.0}
    assert em.get_entry_price(row, "open") == 200.0, (
        "use_adjusted_price=False 시 원 가격(open)이 사용되어야 함"
    )


# ============================================================================
# §17.10 — 동시 신호 우선순위 결정론
# 관련 커버 파일: PRI::test_priority_trading_value_desc_orders_by_close_times_volume
#                PRI::test_priority_trading_value_desc_tie_breaker_symbol_asc
#                G01::test_golden_03_full_determinism_10_runs
# ============================================================================


def test_13_17_10_concurrent_signal_priority_determinism():
    """§17.10 — 동시 매수 신호에서 priority 알고리즘이 결정론적으로 동작.

    같은 입력에 대해 5회 실행해도 매수 종목 순서가 동일해야 함.
    """
    import pandas as pd

    SYMBOL_A = "000001"
    SYMBOL_B = "000002"
    SYMBOL_C = "000003"

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]

    def _multi_df(closes, volumes=None):
        n = len(dates)
        vols = volumes or [10_000.0] * n
        df = pd.DataFrame(
            {
                "date": dates,
                "adj_open": closes,
                "adj_high": closes,
                "adj_low": closes,
                "adj_close": closes,
                "adj_volume": vols,
            }
        )
        df["next_open"] = df["adj_open"].shift(-1)
        df["next_volume"] = df["adj_volume"].shift(-1)
        return df

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }

    all_buy_orders: list[list[str]] = []
    for _ in range(5):
        portfolio = Portfolio(initial_cash=1_000_000)
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
        config = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="trading_value_desc",
        )
        engine = BacktestEngine(StrategyEngine(strategy), portfolio, em, config)
        # B: vol 5000 (가장 큼), C: vol 2000, A: vol 1000 → 순서: B, C, A
        df_a = _multi_df([100, 100, 110, 110], volumes=[10_000, 10_000, 1_000, 10_000])
        df_b = _multi_df([100, 100, 110, 110], volumes=[10_000, 10_000, 5_000, 10_000])
        df_c = _multi_df([100, 100, 110, 110], volumes=[10_000, 10_000, 2_000, 10_000])
        result = engine.run({SYMBOL_A: df_a, SYMBOL_B: df_b, SYMBOL_C: df_c})
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        all_buy_orders.append([b["symbol"] for b in buys])

    assert all(o == all_buy_orders[0] for o in all_buy_orders), (
        f"동시 신호 priority 결정론 깨짐: {all_buy_orders}"
    )
    # trading_value 기준으로 B, C가 선택돼야 함
    assert all_buy_orders[0] == [SYMBOL_B, SYMBOL_C], (
        f"priority 순서 불일치: {all_buy_orders[0]}"
    )


def test_13_17_10_symbol_asc_tiebreaker_determinism():
    """§17.10 보완 — trading_value 동점 시 symbol_asc tie-breaker 결정론.

    3종목 모두 동일 trading_value → symbol ASC로 000001, 000002 선택.
    """
    import pandas as pd

    SYMBOL_A = "000001"
    SYMBOL_B = "000002"
    SYMBOL_C = "000003"

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]

    def _uniform_df():
        df = pd.DataFrame(
            {
                "date": dates,
                "adj_open": [100, 100, 110, 110],
                "adj_high": [100, 100, 110, 110],
                "adj_low": [100, 100, 110, 110],
                "adj_close": [100, 100, 110, 110],
                "adj_volume": [10_000.0] * 4,
            }
        )
        df["next_open"] = df["adj_open"].shift(-1)
        df["next_volume"] = df["adj_volume"].shift(-1)
        return df

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }

    all_orders: list[list[str]] = []
    for _ in range(5):
        portfolio = Portfolio(initial_cash=1_000_000)
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
        config = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="trading_value_desc",
        )
        engine = BacktestEngine(StrategyEngine(strategy), portfolio, em, config)
        result = engine.run(
            {SYMBOL_A: _uniform_df(), SYMBOL_B: _uniform_df(), SYMBOL_C: _uniform_df()}
        )
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        all_orders.append([b["symbol"] for b in buys])

    assert all(o == all_orders[0] for o in all_orders), (
        f"tie-breaker 결정론 깨짐: {all_orders}"
    )
    assert all_orders[0] == [SYMBOL_A, SYMBOL_B], (
        f"symbol_asc tie-breaker 순서 불일치: {all_orders[0]}"
    )


# ============================================================================
# §17.11 — random_seed 동일 시 동일 결과
# 관련 커버 파일: PRI::test_priority_random_same_seed_deterministic
#                PRI::test_priority_random_seed_zero_is_deterministic
#                G01::test_golden_01_determinism_two_runs
# ============================================================================


def test_13_17_11_same_random_seed_yields_same_result():
    """§17.11 — priority_method='random' + random_seed 동일 시 동일 결과.

    같은 seed로 3회 실행 → 매수 종목 순서, final_equity 모두 동일.
    """
    import pandas as pd

    SYMBOL_A = "000001"
    SYMBOL_B = "000002"
    SYMBOL_C = "000003"

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]

    def _df():
        df = pd.DataFrame(
            {
                "date": dates,
                "adj_open": [100, 100, 110, 110],
                "adj_high": [100, 100, 110, 110],
                "adj_low": [100, 100, 110, 110],
                "adj_close": [100, 100, 110, 110],
                "adj_volume": [10_000.0] * 4,
            }
        )
        df["next_open"] = df["adj_open"].shift(-1)
        df["next_volume"] = df["adj_volume"].shift(-1)
        return df

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }

    finals: list[float] = []
    buy_orders: list[list[str]] = []
    SEED = 42

    for _ in range(3):
        portfolio = Portfolio(initial_cash=1_000_000)
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
        config = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="random",
            random_seed=SEED,
        )
        engine = BacktestEngine(StrategyEngine(strategy), portfolio, em, config)
        result = engine.run(
            {SYMBOL_A: _df(), SYMBOL_B: _df(), SYMBOL_C: _df()}
        )
        buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
        finals.append(result.final_equity)
        buy_orders.append([b["symbol"] for b in buys])

    assert all(f == finals[0] for f in finals), (
        f"random_seed 동일 시 final_equity가 달라짐: {finals}"
    )
    assert all(o == buy_orders[0] for o in buy_orders), (
        f"random_seed 동일 시 매수 순서가 달라짐: {buy_orders}"
    )


def test_13_17_11_seed_zero_is_deterministic():
    """§17.11 보완 — seed=0도 결정론 (truthy 체크 버그 방지).

    if seed:  처럼 쓰면 seed=0이 falsy라 무시됨 → 회귀 방지.
    """
    import pandas as pd

    SYMBOL_A = "000001"
    SYMBOL_B = "000002"
    SYMBOL_C = "000003"

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]

    def _df():
        df = pd.DataFrame(
            {
                "date": dates,
                "adj_open": [100, 100, 110, 110],
                "adj_high": [100, 100, 110, 110],
                "adj_low": [100, 100, 110, 110],
                "adj_close": [100, 100, 110, 110],
                "adj_volume": [10_000.0] * 4,
            }
        )
        df["next_open"] = df["adj_open"].shift(-1)
        df["next_volume"] = df["adj_volume"].shift(-1)
        return df

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }

    finals: list[float] = []
    for _ in range(3):
        portfolio = Portfolio(initial_cash=1_000_000)
        em = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
        config = BacktestConfig(
            symbol=SYMBOL_A,
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
            priority_method="random",
            random_seed=0,  # seed=0은 falsy → 버그 발생 소지
        )
        engine = BacktestEngine(StrategyEngine(strategy), portfolio, em, config)
        result = engine.run(
            {SYMBOL_A: _df(), SYMBOL_B: _df(), SYMBOL_C: _df()}
        )
        finals.append(result.final_equity)

    assert all(f == finals[0] for f in finals), (
        f"seed=0 결정론 깨짐: {finals}"
    )
