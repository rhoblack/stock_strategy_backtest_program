"""단일 종목 BacktestEngine 시나리오 테스트.

정확성 정책 13.3 (일중 익절/손절) / 13.4 (갭/거래정지) / 13.16 (이벤트 우선순위)
적용을 검증.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

SYMBOL = "005930"


# ========================================================================
# 헬퍼: 시나리오 데이터 만들기
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
    # next_open / next_volume: 한 칸 shift(-1) (마지막은 NaN)
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


def _trivial_entry_strategy(
    *,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    max_holding_days: int | None = None,
    exit_signal_below_ma: bool = False,
) -> dict:
    """가격이 1일 MA 위면 매수, 옵션으로 exit_position 추가.

    1일 MA는 자기 자신이라 사실상 항상 True가 아니라 NaN-handling으로 첫날 False.
    1일 MA 위 = 가격 > 그 가격 자체 = False. 대신 ma_period=1 + operator='>' → 항상 False.
    그래서 ma_period=2 사용.
    """
    exit_position_conds = []
    if take_profit is not None:
        exit_position_conds.append({"type": "take_profit", "percent": take_profit, "trigger": "intraday_high"})
    # stop_loss / max_holding_days는 조건 함수 미등록이라 schema에 직접 명시 (engine이 직접 평가)
    if stop_loss is not None:
        exit_position_conds.append({"type": "stop_loss", "percent": stop_loss})
    if max_holding_days is not None:
        exit_position_conds.append({"type": "max_holding_days", "days": max_holding_days})

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        }
    }
    if exit_position_conds:
        strategy["exit_position"] = {"logic": "OR", "conditions": exit_position_conds}
    if exit_signal_below_ma:
        strategy["exit_signal"] = {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": "<"}],
        }
    return strategy


def _make_engine(strategy: dict, *, initial_cash: float = 1_000_000, position_size: float = 500_000):
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=0.0,  # Phase 1 테스트 단순화
        tax_rate=0.0,
        slippage=0.0,
        tick_rounding="nearest",  # 호가 단위 노이즈 제거
    )
    config = BacktestConfig(
        symbol=SYMBOL,
        start_date=date(2024, 1, 1),
        end_date=date(2030, 12, 31),
        position_size_amount=position_size,
        initial_cash=initial_cash,
    )
    return BacktestEngine(StrategyEngine(strategy), portfolio, execution_model, config)


# ========================================================================
# 시나리오: 매수 → 익절
# ========================================================================


def test_entry_signal_buys_at_next_open():
    """가격 100 → 100 → 110 → 110:
    Day0~1까지 가격 동일 (entry False), Day2에 110으로 ma>1 → entry True
    Day3 시가 110에 매수.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 100, 110, 110])
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    # SYMBOL이 매수되었는지
    buy_logs = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buy_logs) == 1
    assert buy_logs[0]["symbol"] == SYMBOL


def test_intraday_take_profit_executes_at_target():
    """매수 후 다음날 high가 익절선 도달 → 익절가 체결.

    Day3 시가는 익절선(117.7) 미만이어야 갭 업이 아니고 일중 익절로 처리.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day1 entry True (110 > MA 105) → Day2 시가 110에 매수
    # Day3: 시가 115 (갭 +4.5%, 익절선 117.7 미만), high 130 (≥ 117.7) → take_profit 117.7
    df = _make_df(
        dates,
        closes=[100, 110, 110, 125],
        opens=[100, 110, 110, 115],
        highs=[100, 110, 110, 130],
        lows=[100, 110, 110, 113],
    )
    engine = _make_engine(_trivial_entry_strategy(take_profit=7.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    sell = sells[0]
    # 매수가 110, 익절가 = 110 * 1.07 = 117.7
    assert sell["price"] == pytest.approx(117.7, abs=0.5)
    assert sell["reason"] == "take_profit"


def test_intraday_stop_loss_executes_at_stop_price():
    """매수 후 일중 low가 손절선 도달 → 손절가 체결."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 매수가 110, 손절선 = 110 * 0.97 = 106.7
    # Day3 low 100 → 손절 106.7
    df = _make_df(
        dates,
        closes=[100, 110, 110, 105],
        opens=[100, 110, 110, 108],
        highs=[100, 110, 110, 109],
        lows=[100, 110, 110, 100],
    )
    engine = _make_engine(_trivial_entry_strategy(stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["price"] == pytest.approx(106.7, abs=0.5)
    assert sells[0]["reason"] == "stop_loss"


def test_simultaneous_take_profit_and_stop_loss_prefers_stop_loss():
    """동일 봉에서 high가 익절선, low가 손절선 둘 다 도달 → 손절 우선
    (정확성 정책 13.3.2)."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 매수가 110, take=7% → 117.7, stop=3% → 106.7
    # Day3: high 120 (>= 117.7), low 100 (<= 106.7) → 둘 다 만족
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110],
        opens=[100, 110, 110, 110],
        highs=[100, 110, 110, 120],
        lows=[100, 110, 110, 100],
    )
    engine = _make_engine(_trivial_entry_strategy(take_profit=7.0, stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["reason"] == "stop_loss"


def test_gap_down_stop_loss_executes_at_open_price():
    """갭 다운으로 시가가 이미 손절선 아래 → 시가 체결, exit_reason='gap_down_stop_loss'."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 매수가 110, 손절선 106.7
    # Day3 시가 100 (< 106.7) → 100에 체결
    df = _make_df(
        dates,
        closes=[100, 110, 110, 102],
        opens=[100, 110, 110, 100],
        highs=[100, 110, 110, 105],
        lows=[100, 110, 110, 95],
    )
    engine = _make_engine(_trivial_entry_strategy(stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["price"] == pytest.approx(100, abs=0.5)
    assert sells[0]["reason"] == "gap_down_stop_loss"


def test_gap_up_take_profit_executes_at_open_price():
    """갭 업으로 시가가 이미 익절선 위 → 시가 체결, exit_reason='gap_up_take_profit'."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # 매수가 110, 익절선 117.7
    # Day3 시가 130 (> 117.7) → 130에 체결
    df = _make_df(
        dates,
        closes=[100, 110, 110, 130],
        opens=[100, 110, 110, 130],
        highs=[100, 110, 110, 132],
        lows=[100, 110, 110, 128],
    )
    engine = _make_engine(_trivial_entry_strategy(take_profit=7.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["price"] == pytest.approx(130, abs=0.5)
    assert sells[0]["reason"] == "gap_up_take_profit"


# ========================================================================
# 갭 / 거래정지 / max_holding
# ========================================================================


def test_max_gap_skip_for_entry_at_open():
    """다음 시가가 +5% 초과 갭상승이면 매수 skip (정확성 정책 13.4.1).

    이후 봉에서 더 이상 entry 신호가 발생하지 않도록 가격 흐름 단조화.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day1 entry True (110>MA 105) → Day2 시가 130 (갭 +18%) → skip
    # Day2 close 100 → Day2 entry False (100 < MA 105)
    df = _make_df(
        dates,
        closes=[100, 110, 100, 100],
        opens=[100, 110, 130, 100],
    )
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 0, f"갭 초과 매수가 발생: {buys}"


def test_no_volume_skips_processing():
    """거래량 0인 날은 매수/매도 모두 skip."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110],
        volumes=[10_000, 10_000, 0, 10_000],  # Day2 거래정지
    )
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    # Day1에 entry True여도 Day2 거래정지로 매수 안 됨
    # → Day3에는 final_entry_signal 봐야 함 (이전 신호는 한 번 흘려보냄)
    # 단순 검증: 매수가 되더라도 day1 신호 → day2 시가는 거래정지로 skip
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    # 이 시나리오에선 거래정지가 한 번 끼어들었지만 day3에 다시 entry True면 day4 매수
    # day3 close=110 > MA=110 → False (== 가 아님). day3 entry=False
    assert len(buys) == 0


def test_max_holding_days_closes_position_at_close():
    """max_holding_days 도달 시 종가 청산."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17, 18, 19)]
    closes = [100, 110, 105, 105, 105, 105, 105, 105]
    df = _make_df(dates, closes=closes)
    # max_holding_days=3 → 매수 후 3일 경과 시 종가 청산
    engine = _make_engine(_trivial_entry_strategy(max_holding_days=3))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["reason"] == "max_holding_days"


# ========================================================================
# exit_signal
# ========================================================================


def test_exit_signal_sells_at_next_open():
    """exit_signal True → 다음날 시가 매도."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # Day0~1: 가격 상승 → entry → Day2 매수 110
    # Day3: 가격 하락 → exit_signal (price < MA)
    # Day4: 시가 매도
    df = _make_df(dates, closes=[100, 110, 110, 95, 95])
    engine = _make_engine(_trivial_entry_strategy(exit_signal_below_ma=True))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) >= 1
    assert sells[0]["reason"] == "exit_signal"


# ========================================================================
# 결정론
# ========================================================================


def test_same_data_same_result_deterministic():
    """같은 입력 5회 반복 시 동일 결과."""
    rng = np.random.default_rng(42)
    n = 50
    dates = [(pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)).date() for i in range(n)]
    closes = (rng.normal(100, 2, n).cumsum() + 100).tolist()
    df = _make_df(dates, closes=closes)

    results = []
    for _ in range(5):
        engine = _make_engine(_trivial_entry_strategy(take_profit=5.0, stop_loss=3.0))
        results.append(engine.run(df))

    # 모든 결과의 final_equity가 동일
    finals = [r.final_equity for r in results]
    assert all(f == finals[0] for f in finals), f"결정론 깨짐: {finals}"

    # 거래 횟수도 동일
    counts = [len(r.trade_executions) for r in results]
    assert all(c == counts[0] for c in counts)


# ========================================================================
# 일별 자산 기록
# ========================================================================


def test_daily_equity_recorded_for_each_day():
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df = _make_df(dates, closes=[100, 100, 100, 100, 100])
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    assert len(result.daily_equity) == 5
    # 매수가 없으니 cash가 변하지 않음
    assert all(eq.cash == 1_000_000 for eq in result.daily_equity)


def test_drawdown_negative_after_loss():
    """손절 후 drawdown이 음수가 되어야 한다."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 100, 100],
        opens=[100, 110, 110, 100, 100],
        lows=[100, 110, 110, 95, 100],
    )
    engine = _make_engine(_trivial_entry_strategy(stop_loss=3.0))
    result = engine.run(df)

    final_drawdown = result.daily_equity[-1].drawdown
    assert final_drawdown <= 0
