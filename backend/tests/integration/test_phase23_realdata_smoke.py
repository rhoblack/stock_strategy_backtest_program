"""Phase 23 step 071: pykrx 실데이터 smoke test.

@pytest.mark.realdata 마커로 기본 pytest 실행에서 자동 skip 됨.
활성화: PYTEST_REALDATA=1 환경변수 또는 --realdata 플래그.

검증 목표 (E23-11 ~ E23-13):
  E23-11: pykrx로 삼성전자(005930) 최근 60일 시세 수집 → 결과 비어있지 않음
  E23-12: 수집된 데이터로 BacktestEngine 실행 (가격>MA(5)) → result 비어있지 않음
  E23-13: 수집 결과에 필수 컬럼 존재 확인
           (date, open, high, low, close, volume, adj_open, adj_high, adj_low, adj_close, adj_volume)

정확성 정책 매핑:
  - 14번 §4.1  PykrxCollector — collect_daily_prices
  - 14번 §7    데이터 검증 (컬럼 형식)
  - 13.7   수정주가 사용 (adj_* 컬럼 존재)
  - CLAUDE.md #5  adj_* 기본 사용
  - look-ahead bias 차단: next_open = shift(-1) (PriceLoader 패턴)

본 파일: tests/integration/test_phase23_realdata_smoke.py
conftest.py의 pytest_collection_modifyitems가 --realdata 없으면 자동 skip.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

# 조건 자동 등록 (BacktestEngine에서 price_vs_ma 사용)
import app.strategy  # noqa: F401

SYMBOL_SAMSUNG = "005930"  # 삼성전자


# ---------------------------------------------------------------------------
# E23-11: pykrx 삼성전자 60일 시세 수집
# ---------------------------------------------------------------------------


@pytest.mark.realdata
def test_pykrx_samsung_60days_ingest():
    """E23-11: pykrx로 005930 최근 60일 시세 수집 → 결과 비어있지 않음.

    정확성 정책 매핑:
      - 14번 §4.1  PykrxCollector.collect_daily_prices
      - 14번 §6.3  재시도 정책 (backoff=(0,) — 테스트는 단건만)
    """
    from app.data_pipeline.collectors.pykrx import PykrxCollector

    end_date = date.today()
    start_date = end_date - timedelta(days=90)  # 60 거래일 확보를 위해 90 캘린더일

    # 테스트용: validate=False로 schema 오류에 덜 엄격하게, backoff=() 로 재시도 없음
    collector = PykrxCollector(backoff=(), validate=False)
    result = collector.collect_daily_prices(
        symbols=[SYMBOL_SAMSUNG],
        start_date=start_date,
        end_date=end_date,
    )

    assert result is not None, "collect_daily_prices 결과가 None"
    assert len(result.rows) > 0, (
        f"수집된 행이 0건: symbol={SYMBOL_SAMSUNG}, "
        f"start={start_date.isoformat()}, end={end_date.isoformat()}"
    )

    # 60 거래일 이상 수집 확인 (시장 휴장일 제외 약 42~45 거래일 기대)
    # 최소 30행을 기준으로 네트워크/API 상태 이상 감지
    assert len(result.rows) >= 30, (
        f"거래일 수가 너무 적음: {len(result.rows)}행 "
        f"(최소 30행 기대)"
    )


# ---------------------------------------------------------------------------
# E23-12: 수집된 데이터로 BacktestEngine 실행
# ---------------------------------------------------------------------------


@pytest.mark.realdata
def test_backtest_with_real_data():
    """E23-12: pykrx 데이터로 BacktestEngine 실행 → result가 None이 아님.

    전략: 가격 > MA(5) 진입, 익절 5% / 손절 3% 청산.

    정확성 정책 매핑:
      - 13.15  look-ahead bias 차단 — next_open shift(-1)
      - 13.12  결정론 — priority_method="none" (default)
      - CLAUDE.md #5  adj_* 컬럼 기본 사용
    """
    import pandas as pd

    from app.backtest.config import BacktestConfig
    from app.backtest.engine import BacktestEngine
    from app.backtest.execution import ExecutionModel
    from app.data_pipeline.collectors.pykrx import PykrxCollector
    from app.portfolio.portfolio import Portfolio
    from app.strategy.engine import StrategyEngine

    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    collector = PykrxCollector(backoff=(), validate=False)
    raw = collector.collect_daily_prices(
        symbols=[SYMBOL_SAMSUNG],
        start_date=start_date,
        end_date=end_date,
    )

    assert len(raw.rows) > 0, "실데이터 수집 실패 — BacktestEngine 실행 불가"

    # RawDailyPriceRow → DataFrame 변환
    rows_list = [
        {
            "date": r.date,
            "adj_open": float(r.adj_open),
            "adj_high": float(r.adj_high),
            "adj_low": float(r.adj_low),
            "adj_close": float(r.adj_close),
            "adj_volume": float(r.adj_volume),
        }
        for r in raw.rows
        if r.symbol == SYMBOL_SAMSUNG
    ]
    assert len(rows_list) > 0, "삼성전자 행이 없음"

    df = pd.DataFrame(rows_list)
    df.sort_values("date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    # look-ahead bias 차단: next_open은 다음날 시가 (shift(-1))
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    df["close"] = df["adj_close"]

    strategy = {
        "entry": {
            "logic": "AND",
            "conditions": [
                {"type": "price_vs_ma", "ma_period": 5, "operator": ">"}
            ],
        },
        "exit_position": {
            "logic": "OR",
            "conditions": [
                {"type": "take_profit", "percent": 5.0, "trigger": "intraday_high"},
                {"type": "stop_loss", "percent": 3.0},
            ],
        },
    }

    portfolio = Portfolio(initial_cash=10_000_000)
    execution_model = ExecutionModel(fee_rate=0.0, tax_rate=0.0, slippage=0.0)
    config = BacktestConfig(
        symbol=SYMBOL_SAMSUNG,
        start_date=df["date"].iloc[0] if hasattr(df["date"].iloc[0], "year") else date(2024, 1, 1),
        end_date=df["date"].iloc[-1] if hasattr(df["date"].iloc[-1], "year") else date.today(),
        initial_cash=10_000_000,
        position_size_amount=5_000_000,
    )
    engine = BacktestEngine(
        StrategyEngine(strategy),
        portfolio,
        execution_model,
        config,
    )

    result = engine.run(df)

    assert result is not None, "BacktestEngine.run이 None을 반환"
    assert result.final_cash >= 0, "final_cash가 음수"
    # trade_executions는 신호 없으면 빈 리스트가 정상
    assert result.trade_executions is not None


# ---------------------------------------------------------------------------
# E23-13: pykrx 응답 컬럼 형식 확인
# ---------------------------------------------------------------------------


@pytest.mark.realdata
def test_pykrx_response_columns():
    """E23-13: 수집 결과에 필수 컬럼 존재 확인.

    필수: date, open, high, low, close, volume (raw)
          adj_open, adj_high, adj_low, adj_close, adj_volume (수정주가)

    정확성 정책 매핑:
      - 14번 §7    데이터 검증 컬럼 형식
      - 13.7   수정주가 사용 일관성 (CLAUDE.md #5)
    """
    from app.data_pipeline.collectors.base import RawDailyPriceRow
    from app.data_pipeline.collectors.pykrx import PykrxCollector

    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    collector = PykrxCollector(backoff=(), validate=False)
    result = collector.collect_daily_prices(
        symbols=[SYMBOL_SAMSUNG],
        start_date=start_date,
        end_date=end_date,
    )

    assert len(result.rows) > 0, "수집 행 0건 — 컬럼 확인 불가"

    sample: RawDailyPriceRow = result.rows[0]

    # RawDailyPriceRow 필드 존재 확인 (dataclass or namedtuple)
    required_fields = (
        "symbol", "date",
        "open", "high", "low", "close", "volume",
        "adj_open", "adj_high", "adj_low", "adj_close", "adj_volume",
    )
    for field in required_fields:
        assert hasattr(sample, field), (
            f"RawDailyPriceRow에 필드 '{field}' 없음 "
            f"(14번 §7 데이터 검증 컬럼 형식 위반)"
        )

    # 수치 타입 검증 (문자열이 아니어야 함)
    assert isinstance(sample.adj_close, (int, float)), (
        f"adj_close 타입 이상: {type(sample.adj_close)} (숫자여야 함)"
    )
    assert sample.adj_close > 0, f"adj_close가 0 이하: {sample.adj_close}"
    assert sample.adj_volume >= 0, f"adj_volume이 음수: {sample.adj_volume}"

    # 심볼 확인
    assert sample.symbol == SYMBOL_SAMSUNG, (
        f"symbol 불일치: {sample.symbol} != {SYMBOL_SAMSUNG}"
    )
