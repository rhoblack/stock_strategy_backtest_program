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
    # stop_loss / max_holding_days / trailing_stop은 010(A1)에서 ConditionRegistry에
    # `requires_position=True`로 등록됨. 012(C1)에서 BacktestEngine이 Registry를
    # 단일 진입점으로 사용하도록 라우팅 통일.
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


# ========================================================================
# C1) ConditionRegistry 라우팅 통일 — 4종 모두 Registry 경유 검증
# ========================================================================


def _trailing_strategy(percent: float) -> dict:
    """trailing_stop 단일 exit_position 전략."""
    return {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "trailing_stop", "percent": percent, "trigger": "intraday_low"}
            ],
        },
    }


def test_exit_position_routes_through_condition_registry(monkeypatch):
    """take_profit / stop_loss / trailing_stop / max_holding_days 4종 모두
    `condition_registry.evaluate_position`로 경유하는지 spy로 검증.

    정확성 정책 13.3 + 03번 §4 + CLAUDE.md 핵심원칙 #2.
    """
    from app.backtest import engine as engine_module
    from app.strategy.registry import condition_registry as real_registry

    called_types: list[str] = []
    real_evaluate_position = real_registry.evaluate_position

    def spy_evaluate_position(condition_type, *, position, market_row, condition):
        called_types.append(condition_type)
        return real_evaluate_position(
            condition_type, position=position, market_row=market_row, condition=condition
        )

    monkeypatch.setattr(
        engine_module.condition_registry,
        "evaluate_position",
        spy_evaluate_position,
    )

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17, 18, 19)]
    # Day1 entry True → Day2 매수 110.
    # 이후 가격 단조 횡보로 일중 trigger 없음 → max_holding_days로 청산.
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110, 110, 110, 110, 110],
        opens=[100, 110, 110, 110, 110, 110, 110, 110],
        highs=[100, 110, 110, 110, 110, 110, 110, 110],
        lows=[100, 110, 110, 110, 110, 110, 110, 110],
    )

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [{"type": "price_vs_ma", "ma_period": 2, "operator": ">"}],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0, "trigger": "intraday_low"},
                {"type": "trailing_stop", "percent": 5.0, "trigger": "intraday_low"},
                {"type": "max_holding_days", "days": 3},
            ],
        },
    }
    engine = _make_engine(strategy)
    engine.run(df)

    # 4종 모두 최소 1회 이상 Registry 경유 호출
    assert "stop_loss" in called_types
    assert "take_profit" in called_types
    assert "trailing_stop" in called_types
    assert "max_holding_days" in called_types


def test_exit_position_priority_stop_before_take_via_registry():
    """동일 봉 stop+take 동시 도달 시 stop 우선 — Registry 라우팅 후에도 보존.

    정확성 정책 13.3.2.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 110],
        opens=[100, 110, 110, 110],
        highs=[100, 110, 110, 120],   # 익절선 117.7 도달
        lows=[100, 110, 110, 100],    # 손절선 106.7 도달
    )
    engine = _make_engine(_trivial_entry_strategy(take_profit=7.0, stop_loss=3.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["reason"] == "stop_loss"


def test_trailing_stop_triggers_via_registry_after_peak_made_prior_day():
    """trailing_stop 정상 트리거 — peak는 전일까지의 high만 사용.

    Day0~1: 가격 상승 (entry 신호)
    Day2: 매수 (110)
    Day3: high 130 → 평가 시점 peak는 110 (전일까지 high), 트리거 없음.
          평가 종료 후 peak가 130으로 갱신.
    Day4: low 100 → peak 130 기준 손절선 = 130*0.95 = 123.5. low 100 ≤ 123.5 → 트리거.
          체결가 = 123.5
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 130, 100],
        opens=[100, 110, 110, 110, 130],
        highs=[100, 110, 110, 130, 130],
        lows=[100, 110, 110, 110, 100],
    )
    engine = _make_engine(_trailing_strategy(percent=5.0))
    result = engine.run(df)

    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    assert len(sells) == 1
    assert sells[0]["reason"] == "trailing_stop"
    assert sells[0]["price"] == pytest.approx(123.5, abs=0.5)


# ========================================================================
# C5) peak_price prev-high 정합화 — look-ahead bias 방지
# ========================================================================


def test_trailing_stop_does_not_use_today_high_for_peak_lookahead():
    """trailing_stop 평가 시점에 그날 high가 peak에 반영되면 안 된다.

    잘못된 구현(현재 종가 또는 그날 high를 즉시 peak로 삽입)이라면:
        Day3에 매수가 110으로 진입 → 같은 봉 high 118로 peak가 즉시 118로 점프 →
        Day3 low 105 ≤ 118*0.95 = 112.1 → 트리거 (잘못 — 같은 봉 회귀 청산)

    올바른 구현(전일까지의 high만 peak):
        Day3 매수 시점 peak = 110, 평가 시점에도 110 → low 105 ≤ 110*0.95 = 104.5 = False
        → 트리거 없음. 같은 봉에서 회귀 청산이 발생하지 않아야 한다.

    정확성 정책 13.3.5 + 13.15.
    """
    # 매수 다음날(Day3)에 high가 폭등하면서 low가 동시에 하락하는 시나리오.
    # 핵심: Day3 같은 봉에서 high를 peak로 즉시 반영하면 잘못된 트리거 발생.
    # 올바른 동작: Day3 평가 시점 peak=110(전일까지 high), low 108은 110*0.95=104.5 미만 아님 → no trigger.
    # 잘못된 동작: Day3 평가 시점 peak=120(그날 high), low 108은 120*0.95=114 미만 → 잘못된 trigger.
    # 이후 Day4부터는 peak=120이 정상 반영되어 평가됨. low를 충분히 높게 둬서
    # Day4 이후 진짜 trailing_stop이 발동하지 않도록 한다 (테스트 간섭 차단).
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 120, 120, 120],
        opens=[100, 110, 110, 110, 120, 120],
        highs=[100, 110, 110, 120, 120, 120],   # Day3 high 120 (peak 후보)
        lows=[100, 110, 110, 108, 119, 119],    # Day3 low 108 (= 같은 봉 내 폭락)
    )
    engine = _make_engine(_trailing_strategy(percent=5.0))
    result = engine.run(df)

    # Day3에 trailing_stop이 트리거되면 look-ahead 버그.
    sells = [ex for ex in result.trade_executions if "SELL" in ex["execution_type"]]
    trailing_sells_on_day3 = [
        s for s in sells if s["reason"] == "trailing_stop" and s["date"] == date(2024, 1, 15)
    ]
    assert trailing_sells_on_day3 == [], (
        f"trailing_stop 평가 시점에 그날 high가 peak로 들어감 (look-ahead): {trailing_sells_on_day3}"
    )


def test_peak_updated_after_exit_evaluation_each_day():
    """exit_position 평가 후 그날 high가 peak에 반영되어 다음날부터 적용된다."""
    from app.backtest.config import BacktestConfig
    from app.backtest.engine import BacktestEngine
    from app.backtest.execution import ExecutionModel
    from app.portfolio.portfolio import Portfolio
    from app.strategy.engine import StrategyEngine

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    df = _make_df(
        dates,
        closes=[100, 110, 110, 115, 115],
        opens=[100, 110, 110, 110, 115],
        highs=[100, 110, 110, 120, 115],
        lows=[100, 110, 110, 110, 110],
    )

    portfolio = Portfolio(initial_cash=1_000_000)
    engine = BacktestEngine(
        StrategyEngine(_trivial_entry_strategy()),
        portfolio,
        ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0, tick_rounding="nearest"),
        BacktestConfig(
            symbol=SYMBOL,
            start_date=date(2024, 1, 1),
            end_date=date(2030, 12, 31),
            position_size_amount=500_000,
            initial_cash=1_000_000,
        ),
    )
    engine.run(df)

    # Day3의 high 120이 평가 후 peak에 반영되어 보존됨
    pos = portfolio.positions.get(SYMBOL)
    assert pos is not None
    assert pos.peak_price == 120, (
        f"peak가 그날 high(120)로 평가 후 갱신되어야 한다: 실제 {pos.peak_price}"
    )


# ========================================================================
# 015) signal_date vs execution_date 분리 — next_open 체결 정합성
# ========================================================================


def test_buy_execution_date_is_next_trading_day_not_signal_date():
    """매수: signal_date == today, execution_date == next_date.

    BUY trade_log의 date / execution_date는 next_date(=다음 거래일),
    signal_date는 today(=신호 발생일)여야 한다 (CLAUDE.md look-ahead 체크리스트
    마지막 줄 — 신호일 종가로 신호, 다음날 시가로 체결).
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 100, 110, 110])
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1
    buy = buys[0]
    # Day2(2024-01-12) 종가에서 entry True → Day3(2024-01-15) 시가 체결
    assert buy["signal_date"] == date(2024, 1, 12), buy
    assert buy["execution_date"] == date(2024, 1, 15), buy
    assert buy["date"] == buy["execution_date"]
    assert buy["signal_date"] != buy["execution_date"]


def test_exit_signal_sell_execution_date_is_next_trading_day():
    """exit_signal 매도: signal_date == today, execution_date == next_date."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16)]
    # Day0~1: 가격 상승 → Day2 매수
    # Day3 (15): 가격 하락 → exit_signal True (시그널)
    # Day4 (16): 시가 매도 (체결)
    df = _make_df(dates, closes=[100, 110, 110, 95, 95])
    engine = _make_engine(_trivial_entry_strategy(exit_signal_below_ma=True))
    result = engine.run(df)

    sells = [
        ex
        for ex in result.trade_executions
        if "SELL" in ex["execution_type"] and ex["reason"] == "exit_signal"
    ]
    assert len(sells) >= 1
    sell = sells[0]
    assert sell["signal_date"] == date(2024, 1, 15), sell
    assert sell["execution_date"] == date(2024, 1, 16), sell
    assert sell["date"] == sell["execution_date"]


def test_intraday_take_profit_signal_equals_execution_date():
    """일중 익절: 당일 체결 — signal_date == execution_date == today."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
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
    assert sell["reason"] == "take_profit"
    # 당일 체결 — signal_date == execution_date
    assert sell["signal_date"] == sell["execution_date"]
    assert sell["execution_date"] == date(2024, 1, 15)


def test_gap_down_stop_loss_signal_equals_execution_date():
    """갭 다운 손절: 당일 시가 체결 — signal_date == execution_date == today."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
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
    sell = sells[0]
    assert sell["reason"] == "gap_down_stop_loss"
    assert sell["signal_date"] == sell["execution_date"]
    assert sell["execution_date"] == date(2024, 1, 15)


def test_max_holding_days_signal_equals_execution_date():
    """max_holding_days: 당일 종가 체결 — signal_date == execution_date == today."""
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15, 16, 17, 18, 19)]
    closes = [100, 110, 105, 105, 105, 105, 105, 105]
    df = _make_df(dates, closes=closes)
    engine = _make_engine(_trivial_entry_strategy(max_holding_days=3))
    result = engine.run(df)

    sells = [
        ex
        for ex in result.trade_executions
        if "SELL" in ex["execution_type"] and ex["reason"] == "max_holding_days"
    ]
    assert len(sells) == 1
    sell = sells[0]
    assert sell["signal_date"] == sell["execution_date"]


def test_last_bar_entry_signal_skipped_when_next_date_missing():
    """마지막 봉에서 entry 신호 발생 → next_date NaT → 매수 skip."""
    # Day0: close=100, Day1: close=110 (entry True via ma_period=2)
    # Day1이 마지막 봉 → next_open / next_date 모두 NaN/NaT → 매수 skip
    dates = [date(2024, 1, 10), date(2024, 1, 11)]
    df = _make_df(dates, closes=[100, 110])
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert buys == [], (
        f"마지막 봉에서 next_date 없어 매수 skip되어야 함. 발생한 BUY: {buys}"
    )


def test_last_bar_exit_signal_skipped_when_next_date_missing():
    """마지막 봉에서 exit_signal True → next_date NaT → 매도 skip (포지션 유지)."""
    # Day0~1 상승(매수 후보 형성), Day2 매수(체결), Day3 하락 (exit_signal True),
    # Day3가 마지막 봉이라면 next_date 없음 → exit_signal 매도 skip.
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 110, 110, 95])
    engine = _make_engine(_trivial_entry_strategy(exit_signal_below_ma=True))
    result = engine.run(df)

    # 매수는 Day2 신호 → Day3(15) 체결로 발생.
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1
    # Day3(15)가 마지막 봉이므로 exit_signal 매도가 skip되어야 함.
    sells = [
        ex
        for ex in result.trade_executions
        if "SELL" in ex["execution_type"] and ex["reason"] == "exit_signal"
    ]
    assert sells == [], (
        f"마지막 봉에서 next_date 없어 exit_signal 매도 skip되어야 함: {sells}"
    )


def test_engine_fills_next_date_when_missing():
    """df에 next_date 컬럼이 없어도 BacktestEngine이 자동으로 채운다.

    PriceLoader가 14번 문서에 맞춰 next_date를 채우기 전 dev 환경 호환성.
    next row의 가격/조건은 보지 않고 date만 1칸 shift — look-ahead 차단.
    """
    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    df = _make_df(dates, closes=[100, 100, 110, 110])
    # next_date 컬럼이 _make_df에서는 채워지지 않음 (체크).
    assert "next_date" not in df.columns
    engine = _make_engine(_trivial_entry_strategy())
    result = engine.run(df)

    # next_open 체결이 정상 동작 → BUY 1건.
    buys = [ex for ex in result.trade_executions if ex["execution_type"] == "BUY"]
    assert len(buys) == 1
    assert buys[0]["execution_date"] == date(2024, 1, 15)


def test_holding_days_uses_execution_date_basis():
    """holding_days = exit_execution_date - entry_execution_date.

    매수 next_open 체결, intraday take_profit 당일 체결 → 보유일수 계산이
    execution_date 기반이므로 1일 단축 효과가 정확히 반영된다.
    """
    from app.backtest.metrics import calculate_metrics

    dates = [date(2024, 1, d) for d in (10, 11, 12, 15)]
    # Day1 close=110 entry True → Day2(12) signal? 아니. 1일 MA=110 이라 False.
    # Day0 100, Day1 110 → ma_period=2 평균=105. 110>105 entry True (Day1).
    # Day2(12) 시가 110 매수 (execution_date=12). signal_date=Day1(11).
    # Day3(15) 시가 115, high 130 → 110*1.07=117.7 익절 → 당일 체결 execution_date=15.
    # holding_days = 15 - 12 = 3일 (exit_execution - entry_execution)
    df = _make_df(
        dates,
        closes=[100, 110, 110, 125],
        opens=[100, 110, 110, 115],
        highs=[100, 110, 110, 130],
        lows=[100, 110, 110, 113],
    )
    engine = _make_engine(_trivial_entry_strategy(take_profit=7.0))
    result = engine.run(df)
    metrics = calculate_metrics(result)

    # holding_days = 15 - 12 = 3
    assert metrics["avg_holding_days"] == pytest.approx(3.0, abs=0.01), metrics
