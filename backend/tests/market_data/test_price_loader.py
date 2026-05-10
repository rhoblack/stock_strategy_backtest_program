"""PriceLoader 검증.

정책 매핑:
    - 13.7 (수정주가): adj_* 컬럼 노출
    - 13.15 (look-ahead): next_*는 단순 shift(-1) — 마지막 row는 NaN/NaT
    - 14.10 (결손 정책): forward-fill 금지 — DB row 없으면 DataFrame에도 없음
    - CLAUDE.md #8 (결정론): date ASC 정렬

015 정합 검증:
    - BacktestEngine이 기대하는 next_open / next_close / next_volume / next_date 자동 채움
    - 마지막 row의 next_*는 NaN/NaT → 마지막 봉 매수/매도 자동 skip
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from app.market_data.local_csv import LocalCsvProvider
from app.market_data.price_loader import (
    PRICE_LOADER_BASE_COLUMNS,
    PRICE_LOADER_COLUMNS,
    PRICE_LOADER_NEXT_COLUMNS,
    PriceLoader,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "csv"


def _seed(db_session, fixture: str = "sample"):
    LocalCsvProvider(root=FIXTURE_ROOT / fixture).ingest_into(db_session)
    db_session.commit()


# ---------------------------------------------------------------------------
# 컬럼 명세
# ---------------------------------------------------------------------------


def test_load_returns_required_columns(db_session):
    _seed(db_session)
    loader = PriceLoader(db_session)
    df = loader.load("005930", date(2024, 1, 2), date(2024, 1, 8))

    # 컬럼 명세는 PRICE_LOADER_COLUMNS 순서로 정확히 일치
    assert list(df.columns) == list(PRICE_LOADER_COLUMNS)
    # base + next_* 합계
    assert set(PRICE_LOADER_BASE_COLUMNS) | set(PRICE_LOADER_NEXT_COLUMNS) == set(PRICE_LOADER_COLUMNS)


def test_load_adj_and_raw_prices_both_present(db_session):
    """13.7: open/close (원 가격) + adj_open/adj_close (수정 가격) 둘 다 노출."""
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 2))
    assert df["open"].iloc[0] == 71000.0
    assert df["adj_open"].iloc[0] == 71000.0
    assert df["close"].iloc[0] == 72100.0
    assert df["adj_close"].iloc[0] == 72100.0
    assert df["volume"].iloc[0] == 15000000.0
    assert df["adj_volume"].iloc[0] == 15000000.0
    assert df["market_cap"].iloc[0] == 430000000000000.0


# ---------------------------------------------------------------------------
# next_* 컬럼 (015 정합)
# ---------------------------------------------------------------------------


def test_next_columns_are_shift_minus_one(db_session):
    """next_open = adj_open.shift(-1) — 다음 거래일의 시가."""
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 8))

    # 1/2의 next_open은 1/3의 adj_open
    assert df.loc[0, "next_open"] == df.loc[1, "adj_open"]
    assert df.loc[0, "next_close"] == df.loc[1, "adj_close"]
    assert df.loc[0, "next_volume"] == df.loc[1, "adj_volume"]
    # next_date도 1/3
    assert df.loc[0, "next_date"] == df.loc[1, "date"]


def test_last_row_next_columns_are_nan(db_session):
    """015 정합: 마지막 row의 next_*는 NaN/NaT — BacktestEngine이 자동 skip."""
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 8))
    last = df.iloc[-1]

    assert pd.isna(last["next_open"])
    assert pd.isna(last["next_close"])
    assert pd.isna(last["next_volume"])
    assert pd.isna(last["next_date"])
    assert pd.isna(last["adj_next_open"])
    assert pd.isna(last["adj_next_close"])


def test_adj_next_columns_mirror_next_columns(db_session):
    """ExecutionModel.get_entry_price(use_adjusted_price=True) 호환 — adj_next_* = next_*."""
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 8))

    for i in range(len(df) - 1):  # 마지막은 NaN이라 비교 불가
        assert df.loc[i, "adj_next_open"] == df.loc[i, "next_open"]
        assert df.loc[i, "adj_next_close"] == df.loc[i, "next_close"]


# ---------------------------------------------------------------------------
# 결정론 — date ASC
# ---------------------------------------------------------------------------


def test_load_sorted_by_date_asc(db_session):
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 8))
    dates = list(df["date"])
    assert dates == sorted(dates)


# ---------------------------------------------------------------------------
# 14.10 결손 정책
# ---------------------------------------------------------------------------


def test_missing_bar_not_in_dataframe(db_session):
    """with_missing fixture: 1/4 결손 봉 → DataFrame에도 없음 (forward-fill 금지)."""
    _seed(db_session, fixture="with_missing")
    df = PriceLoader(db_session).load("005930", date(2024, 1, 1), date(2024, 1, 8))

    dates = [d.isoformat() for d in df["date"]]
    assert dates == ["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08"]
    assert "2024-01-04" not in dates

    # 결손 직전 row(1/3)의 next_open은 1/5의 adj_open (다음 row), 1/4가 아님
    # 즉 PriceLoader는 캘린더 거래일이 아닌 "DB에 존재하는 다음 row"의 가격을 next로 봄
    row_3 = df[df["date"] == date(2024, 1, 3)].iloc[0]
    row_5 = df[df["date"] == date(2024, 1, 5)].iloc[0]
    assert row_3["next_open"] == row_5["adj_open"]
    assert row_3["next_date"] == row_5["date"]


# ---------------------------------------------------------------------------
# 빈 결과
# ---------------------------------------------------------------------------


def test_load_empty_when_no_data(db_session):
    """데이터 없는 종목/기간 → 빈 DataFrame (컬럼 명세는 동일)."""
    _seed(db_session)
    df = PriceLoader(db_session).load("999999", date(2024, 1, 1), date(2024, 1, 8))
    assert len(df) == 0
    assert list(df.columns) == list(PRICE_LOADER_COLUMNS)


def test_load_empty_when_date_range_outside(db_session):
    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2030, 1, 1), date(2030, 12, 31))
    assert len(df) == 0


# ---------------------------------------------------------------------------
# 015 BacktestEngine 호환 — load 결과를 엔진에 넣어 실행
# ---------------------------------------------------------------------------


def test_loaded_df_runs_through_backtest_engine(db_session):
    """PriceLoader 결과를 BacktestEngine.run에 그대로 전달 가능 (smoke)."""
    from app.backtest.config import BacktestConfig
    from app.backtest.engine import BacktestEngine
    from app.backtest.execution import ExecutionModel
    from app.portfolio.cash_manager import CashManager
    from app.portfolio.portfolio import Portfolio
    from app.strategy.engine import StrategyEngine

    _seed(db_session)
    df = PriceLoader(db_session).load("005930", date(2024, 1, 2), date(2024, 1, 8))
    assert len(df) == 5

    # 최소 전략: 신호 항상 False (체결 0건이지만 엔진은 끝까지 돌아야 함)
    strategy = {
        "entry": {"logic": "AND", "conditions": []},
        "exit_signal": {"logic": "OR", "conditions": []},
        "exit_position": {"conditions": []},
        "filters": {"logic": "AND", "conditions": []},
    }
    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.00015, tax_rate=0.0018, slippage=0.0)
    config = BacktestConfig(
        symbol="005930",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 8),
        position_size_amount=10_000_000,
        initial_cash=10_000_000,
    )
    cash_manager = CashManager(rule=None, execution_model=execution_model)
    strategy_engine = StrategyEngine(strategy_json=strategy)
    engine = BacktestEngine(
        config=config,
        portfolio=portfolio,
        execution_model=execution_model,
        strategy_engine=strategy_engine,
        cash_manager=cash_manager,
    )

    result = engine.run(df)
    # smoke: 엔진이 5개 row를 끝까지 처리해 daily_equity 5건 생성 (KeyError 없음).
    # 신호 evaluation 결과는 본 테스트의 관심사 아님 (조건 0개 → vacuous truth로
    # 매수/매도 발생할 수 있음). 핵심은 PriceLoader의 컬럼 명세가 BacktestEngine과
    # 정합한지 (next_open / next_close / next_volume / next_date / adj_*).
    assert len(result.daily_equity) == 5
    assert result.initial_cash == 10_000_000
    # 015 정합: 마지막 봉의 next_*는 NaN — 마지막 봉에서 새 매수 발생 안 함
    last_buys_on_last_day = [
        t for t in result.trade_executions
        if t["execution_date"] == date(2024, 1, 8) and t["execution_type"] == "BUY"
    ]
    assert last_buys_on_last_day == []
