"""Phase 13 통합 시나리오 테스트.

검증 목표:
  1. KRW int 전환 (13-s): 백테스트 결과의 정수 보존이 end-to-end로 일관성 있게 전달.
  2. ORDER BY 표준화 (13-t): 반복 실행 시 동일 순서 보장.
  3. CancellationToken 엔진 전파 (10-q): cancel 요청이 실제 실행 중인 엔진에 전달.
  4. 에러 카탈로그 §7.1 (10-r): 코드들이 CODE_STATUS_MAP에 완전 포함.
  5. alembic revision chain (12-i): 갭 없이 연속됨.

정확성 정책 매핑:
  - CLAUDE.md #7: KRW 원화는 정수로 저장/전달 (float 누적 오차 방지)
  - CLAUDE.md #8: ORDER BY 결정론 (dict 순서 의존 금지)
  - 13번 §17.1~§17.11: test_accuracy_policy.py에서 1:1 커버 (본 파일은 e2e 흐름 검증)
  - 10번 §4.4: cancel 엔진 전파
  - 10번 §7.1: 에러 코드 카탈로그 25개

참고: 본 파일은 test-engineer 에이전트가 Phase 13 완료 검증 시 신규 작성.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 5개 기본 조건 자동 등록
import app.strategy  # noqa: F401
from app.backtest.config import BacktestConfig
from app.backtest.engine import BacktestEngine
from app.backtest.execution import ExecutionModel
from app.backtest.metrics import calculate_metrics
from app.core.cancellation import (
    CancellationToken,
    cancel_run,
    get_token,
    register_token,
    unregister_token,
)
from app.portfolio.portfolio import Portfolio
from app.strategy.engine import StrategyEngine

# ---------------------------------------------------------------------------
# 공용 헬퍼 — test_phase1_golden.py 패턴 준수
# ---------------------------------------------------------------------------

def _make_price_df(n: int = 60, seed: int = 42) -> pd.DataFrame:
    """결정론적 합성 일봉 시계열 (look-ahead bias 없음).

    adj_* 컬럼 + next_open/next_volume 포함 — BacktestEngine 호환 형식.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=0.001, scale=0.02, size=n)
    closes = 10_000 * np.exp(np.cumsum(returns))
    closes = closes.round(0)

    high_mults = 1 + rng.uniform(0.001, 0.015, n)
    low_mults = 1 - rng.uniform(0.001, 0.015, n)
    open_jitter = rng.uniform(-0.005, 0.005, n)

    opens = (closes * (1 + open_jitter)).round(0)
    highs = (np.maximum(closes, opens) * high_mults).round(0)
    lows = (np.minimum(closes, opens) * low_mults).round(0)

    base_date = date(2023, 1, 2)
    dates = [base_date + timedelta(days=i) for i in range(n)]

    df = pd.DataFrame(
        {
            "date": dates,
            "adj_open": opens,
            "adj_high": highs,
            "adj_low": lows,
            "adj_close": closes,
            "adj_volume": np.full(n, 50_000.0),
        }
    )
    df["next_open"] = df["adj_open"].shift(-1)
    df["next_volume"] = df["adj_volume"].shift(-1)
    return df


_SIMPLE_STRATEGY = {
    "entry": {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 5.0},
            {"type": "max_holding_days", "days": 20},
        ],
    },
}

_TAKE_PROFIT_STRATEGY = {
    "entry": {
        "logic": "AND",
        "conditions": [{"type": "price_vs_ma", "ma_period": 5, "operator": ">"}],
    },
    "exit_position": {
        "logic": "OR",
        "conditions": [
            {"type": "take_profit", "percent": 3.0},
            {"type": "max_holding_days", "days": 20},
        ],
    },
}


def _run(
    strategy: dict,
    df: pd.DataFrame,
    *,
    initial_cash: int = 10_000_000,
    position_size_amount: float = 2_000_000,
    fee_rate: float = 0.00015,
    tax_rate: float = 0.0018,
    slippage: float = 0.0005,
    cancel_token: CancellationToken | None = None,
):
    """BacktestEngine end-to-end 실행 헬퍼.

    test_phase1_golden.py의 _run()과 동일한 패턴 사용.
    """
    portfolio = Portfolio(initial_cash=initial_cash)
    execution_model = ExecutionModel(
        fee_rate=fee_rate,
        tax_rate=tax_rate,
        slippage=slippage,
    )
    config = BacktestConfig(
        symbol="005930",
        start_date=df["date"].iloc[0] if "date" in df.columns else date(2023, 1, 2),
        end_date=df["date"].iloc[-1] if "date" in df.columns else date(2023, 12, 31),
        position_size_amount=position_size_amount,
        initial_cash=initial_cash,
    )
    engine = BacktestEngine(
        strategy_engine=StrategyEngine(strategy),
        portfolio=portfolio,
        execution_model=execution_model,
        config=config,
    )
    return engine.run(df, cancel_token=cancel_token)


# ---------------------------------------------------------------------------
# 시나리오 1: KRW int 전환 end-to-end (13-s)
# ---------------------------------------------------------------------------


class TestKrwIntEndToEnd:
    """KRW int 전환이 BacktestEngine → Portfolio → 결과 지표까지 일관되는지 검증.

    CLAUDE.md #7: float 누적 오차를 막기 위해 원화는 정수로 처리.
    """

    def test_initial_cash_is_int_throughout_backtest(self):
        """초기 예수금이 int로 시작해서 결과의 현금 필드가 int를 유지해야 한다."""
        df = _make_price_df()
        result = _run(_SIMPLE_STRATEGY, df)

        assert isinstance(result.initial_cash, int), (
            f"initial_cash가 int가 아님: {type(result.initial_cash)}"
        )
        assert isinstance(result.final_cash, int), (
            f"final_cash가 int가 아님: {type(result.final_cash)}"
        )

    def test_trade_execution_amounts_are_int(self):
        """거래 체결 금액 (gross_amount, fee, tax, net_amount)이 모두 int여야 한다."""
        df = _make_price_df()
        result = _run(_SIMPLE_STRATEGY, df)

        if not result.trade_executions:
            pytest.skip("거래 체결이 없어 검증 불가")

        for ex_log in result.trade_executions:
            for field in ("gross_amount", "fee", "tax", "net_amount"):
                if field in ex_log:
                    val = ex_log[field]
                    assert isinstance(val, int), (
                        f"거래 체결 '{field}'이 int가 아님: {type(val).__name__} = {val}"
                    )

    def test_daily_equity_values_are_int(self):
        """DailyEquity의 cash/stock_value/total_equity가 int여야 한다."""
        df = _make_price_df()
        result = _run(_SIMPLE_STRATEGY, df)

        if not result.daily_equity:
            pytest.skip("daily_equity가 없어 검증 불가")

        for eq in result.daily_equity[:5]:  # 처음 5개만 확인
            # DailyEquity는 dataclass이므로 hasattr로 접근
            for field in ("cash", "stock_value", "total_equity"):
                if hasattr(eq, field):
                    val = getattr(eq, field)
                    assert isinstance(val, int), (
                        f"DailyEquity '{field}'이 int가 아님: {type(val).__name__} = {val}"
                    )


# ---------------------------------------------------------------------------
# 시나리오 2: ORDER BY 결정론 (13-t)
# ---------------------------------------------------------------------------


class TestOrderByDeterminism:
    """ORDER BY 표준화가 반복 실행 시 동일 순서를 보장하는지 검증.

    CLAUDE.md #8: dict 순서에 의존하면 결정론이 깨진다.
    """

    def test_multiple_runs_produce_same_execution_order(self):
        """동일 조건으로 백테스트를 2회 실행하면 trade_executions 순서가 동일해야 한다."""
        df = _make_price_df(seed=123)
        r1 = _run(_SIMPLE_STRATEGY, df)
        r2 = _run(_SIMPLE_STRATEGY, df)

        assert len(r1.trade_executions) == len(r2.trade_executions), (
            f"실행 횟수 불일치: {len(r1.trade_executions)} vs {len(r2.trade_executions)}"
        )

        for i, (e1, e2) in enumerate(
            zip(r1.trade_executions, r2.trade_executions, strict=False)
        ):
            assert e1.get("execution_date") == e2.get("execution_date"), (
                f"[{i}] execution_date 불일치: "
                f"{e1.get('execution_date')} vs {e2.get('execution_date')}"
            )
            assert e1.get("execution_type") == e2.get("execution_type"), (
                f"[{i}] execution_type 불일치"
            )

    def test_metrics_are_identical_across_runs(self):
        """동일 데이터로 반복 실행 시 metrics 결과가 완전히 동일해야 한다."""
        df = _make_price_df(seed=77)
        m1 = calculate_metrics(_run(_SIMPLE_STRATEGY, df))
        m2 = calculate_metrics(_run(_SIMPLE_STRATEGY, df))

        assert m1["trade_count"] == m2["trade_count"], "trade_count 불일치"
        assert m1["final_equity"] == m2["final_equity"], "final_equity 불일치"
        assert m1["win_rate"] == pytest.approx(m2["win_rate"], rel=1e-9), "win_rate 불일치"


# ---------------------------------------------------------------------------
# 시나리오 3: CancellationToken 엔진 전파 (10-q)
# ---------------------------------------------------------------------------


class TestCancellationTokenPropagation:
    """CancellationToken이 BacktestEngine에 정상 전파되는지 검증.

    10번 §4.4: cancel 요청 시 실행 중인 BacktestEngine이 중단되어야 한다.
    """

    def test_pre_cancelled_token_stops_engine_immediately(self):
        """실행 전 이미 취소된 토큰으로 run()을 호출하면 즉시 중단되어야 한다."""
        from app.core.cancellation import BacktestCancelledError

        df = _make_price_df(n=100)
        token = CancellationToken(run_id=12345)
        token.cancel()  # 사전에 취소

        with pytest.raises(BacktestCancelledError):
            _run(_SIMPLE_STRATEGY, df, cancel_token=token)

    def test_token_registry_register_and_unregister(self):
        """register_token이 토큰을 생성하고 get_token/unregister_token으로 관리 가능."""
        run_id = 99998
        unregister_token(run_id)  # 기존 토큰 정리

        token = register_token(run_id)
        assert token is not None, "register_token이 None을 반환함"
        assert not token.is_cancelled(), "새 토큰이 이미 취소 상태임"

        retrieved = get_token(run_id)
        assert retrieved is token, "등록된 토큰과 조회된 토큰이 다름"

        unregister_token(run_id)
        assert get_token(run_id) is None, "해제 후 토큰이 남아 있음"

    def test_cancel_sets_token_state(self):
        """cancel() 호출 후 is_cancelled()가 True여야 한다."""
        token = CancellationToken()
        assert not token.is_cancelled(), "초기 상태가 cancelled이면 안 됨"

        token.cancel()
        assert token.is_cancelled(), "cancel() 후 is_cancelled()가 False임"

    def test_cancel_run_via_registry(self):
        """cancel_run(run_id) 호출 시 등록된 토큰에 취소 신호가 전달된다."""
        run_id = 99997
        unregister_token(run_id)

        token = register_token(run_id)
        assert not token.is_cancelled()

        result = cancel_run(run_id)
        assert result is True, "cancel_run이 False를 반환함 (토큰이 없음)"
        assert token.is_cancelled(), "cancel_run 후 토큰이 취소 상태가 아님"

        unregister_token(run_id)

    def test_cancel_run_returns_false_for_unregistered(self):
        """등록되지 않은 run_id에 cancel_run을 호출하면 False를 반환해야 한다."""
        run_id = 99996
        unregister_token(run_id)  # 없어도 안전하게 정리
        result = cancel_run(run_id)
        assert result is False, "미등록 run_id에 cancel_run이 True를 반환함"


# ---------------------------------------------------------------------------
# 시나리오 4: 에러 카탈로그 §7.1 완전 커버리지 (10-r)
# ---------------------------------------------------------------------------


class TestErrorCatalogCoverage:
    """에러 코드 카탈로그 §7.1의 코드들이 CODE_STATUS_MAP에 모두 포함되는지 검증.

    10번 §7.1: NOT_FOUND, VALIDATION_ERROR 등 임시 코드는 제거됨.
    """

    # 10번 §7.1 카탈로그에서 반드시 존재해야 하는 핵심 코드 (실제 구현 기준)
    REQUIRED_CODES = {
        "INVALID_STRATEGY_JSON",
        "INVALID_OPERATOR",
        "INVALID_PARAMETER_VALUE",
        "STRATEGY_NOT_FOUND",
        "DUPLICATE_STRATEGY_NAME",
        "BACKTEST_RUN_NOT_FOUND",
        "BACKTEST_ALREADY_RUNNING",
        "BACKTEST_NOT_RUNNING",
        "BACKTEST_TIMEOUT",
        "INSUFFICIENT_PRICE_DATA",
        "TRADING_CALENDAR_MISSING",
        "INVALID_DATE_RANGE",
        "MARKET_DATA_NOT_FOUND",
        "SYMBOL_NOT_FOUND",
        "UNIVERSE_EMPTY",
        "UNIVERSE_PREVIEW_FAILED",
        "UNAUTHORIZED",
        "FORBIDDEN",
        "RATE_LIMIT_EXCEEDED",
        "EXPORT_FAILED",
        "EXPORT_TOO_LARGE",
        "POSITION_CONDITION_MISUSE",
        "TIMESERIES_CONDITION_MISUSE",
    }

    # 임시 코드: 존재하면 안 됨 (정식화 완료 확인)
    BANNED_CODES = {"VALIDATION_ERROR", "NOT_FOUND", "METHOD_NOT_ALLOWED", "HTTP_ERROR"}

    def test_required_codes_in_status_map(self):
        """§7.1 필수 코드들이 CODE_STATUS_MAP에 모두 포함되어야 한다."""
        from app.api.errors import CODE_STATUS_MAP

        missing = self.REQUIRED_CODES - set(CODE_STATUS_MAP.keys())
        assert not missing, f"CODE_STATUS_MAP에 누락된 코드: {sorted(missing)}"

    def test_banned_codes_absent(self):
        """임시 코드(VALIDATION_ERROR, NOT_FOUND 등)는 CODE_STATUS_MAP에 없어야 한다."""
        from app.api.errors import CODE_STATUS_MAP

        present = self.BANNED_CODES & set(CODE_STATUS_MAP.keys())
        assert not present, f"비표준 임시 코드가 아직 존재함: {sorted(present)}"

    def test_all_codes_map_to_valid_http_status(self):
        """모든 코드의 HTTP 상태 코드가 4xx 또는 5xx여야 한다."""
        from app.api.errors import CODE_STATUS_MAP

        for code, status in CODE_STATUS_MAP.items():
            assert 400 <= status < 600, (
                f"코드 '{code}'의 HTTP 상태 {status}가 4xx/5xx가 아님"
            )

    def test_catalog_has_at_least_25_codes(self):
        """CODE_STATUS_MAP에 §7.1 기준 최소 25개 이상의 코드가 있어야 한다."""
        from app.api.errors import CODE_STATUS_MAP

        assert len(CODE_STATUS_MAP) >= 25, (
            f"CODE_STATUS_MAP의 코드 수가 25개 미만: {len(CODE_STATUS_MAP)}개"
        )


# ---------------------------------------------------------------------------
# 시나리오 5: alembic revision chain 연속성 (12-i)
# ---------------------------------------------------------------------------


class TestAlembicRevisionChain:
    """alembic revision이 갭 없이 연속되는지 검증.

    12번 §15 (테스트 표준 구조) + CLAUDE.md #9 (alembic 마이그레이션 영속화).
    """

    def test_head_revision_is_single(self):
        """alembic head revision이 정확히 1개여야 한다 (브랜치 없음)."""
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory

        _repo_root = Path(__file__).resolve().parents[3]
        alembic_cfg = AlembicConfig(str(_repo_root / "backend" / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_repo_root / "backend" / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///:memory:")

        script = ScriptDirectory.from_config(alembic_cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"alembic head가 1개가 아님 (브랜치 존재): {heads}"

    def test_revision_chain_has_no_gaps(self):
        """alembic revision chain에 갭이 없어야 한다 (모든 revision이 연속)."""
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory

        _repo_root = Path(__file__).resolve().parents[3]
        alembic_cfg = AlembicConfig(str(_repo_root / "backend" / "alembic.ini"))
        alembic_cfg.set_main_option("script_location", str(_repo_root / "backend" / "alembic"))
        alembic_cfg.set_main_option("sqlalchemy.url", "sqlite:///:memory:")

        script = ScriptDirectory.from_config(alembic_cfg)
        revisions = list(script.walk_revisions())
        assert len(revisions) > 0, "revision이 하나도 없음"

        rev_ids = {rev.revision for rev in revisions}
        for rev in revisions:
            if rev.down_revision is not None:
                down_revs = (
                    rev.down_revision
                    if isinstance(rev.down_revision, tuple)
                    else (rev.down_revision,)
                )
                for dr in down_revs:
                    assert dr in rev_ids, (
                        f"Revision '{rev.revision}'의 down_revision '{dr}'이 "
                        f"revision 이력에 없음 — 갭 발생"
                    )


# ---------------------------------------------------------------------------
# 시나리오 6: Phase 13 전체 e2e 흐름 (종합)
# ---------------------------------------------------------------------------


class TestPhase13EndToEnd:
    """Phase 13 전체 변경이 통합되어 정상 동작하는지 확인하는 종합 e2e 테스트."""

    def test_full_backtest_int_preservation_and_metrics(self):
        """백테스트 전체 흐름에서 KRW int 보존 + 지표 계산이 일관성 있어야 한다.

        CLAUDE.md #7 + #8: 정수 보존과 결정론이 동시 성립.
        """
        df = _make_price_df(n=80, seed=2024)
        r1 = _run(_TAKE_PROFIT_STRATEGY, df)
        r2 = _run(_TAKE_PROFIT_STRATEGY, df)
        m1 = calculate_metrics(r1)
        m2 = calculate_metrics(r2)

        # KRW int 보존
        assert isinstance(r1.initial_cash, int), "initial_cash가 int가 아님"
        assert isinstance(r1.final_cash, int), "final_cash가 int가 아님"

        # 결정론
        assert m1["trade_count"] == m2["trade_count"], "결정론 위반: trade_count 불일치"
        assert m1["final_equity"] == m2["final_equity"], "결정론 위반: final_equity 불일치"

        # 지표 타입
        assert isinstance(m1["trade_count"], int), "trade_count가 int가 아님"
        assert isinstance(m1["total_return_pct"], float), "total_return_pct가 float가 아님"

    def test_cancel_token_does_not_affect_normal_run(self):
        """취소하지 않은 토큰을 주입해도 백테스트가 정상 완료되어야 한다.

        10번 §4.4: cancel 토큰이 없거나 취소되지 않은 경우 엔진은 정상 실행.
        """
        df = _make_price_df(n=30, seed=55)
        token = CancellationToken(run_id=None)  # 취소하지 않음
        result = _run(_SIMPLE_STRATEGY, df, initial_cash=5_000_000, cancel_token=token)

        assert result is not None, "cancel_token 미취소 시 run()이 None을 반환함"
        assert isinstance(result.final_cash, int), "final_cash가 int가 아님"

    def test_krw_int_and_determinism_combined(self):
        """KRW int 전환 + ORDER BY 결정론이 동시에 성립해야 한다.

        CLAUDE.md #7 + #8: Phase 13의 핵심 개선사항 통합 검증.
        3회 실행 모두 동일한 final_cash (정수)를 반환해야 한다.
        """
        df = _make_price_df(n=50, seed=314)

        runs = [_run(_TAKE_PROFIT_STRATEGY, df) for _ in range(3)]

        for i in range(1, 3):
            assert runs[0].final_cash == runs[i].final_cash, (
                f"run[0].final_cash={runs[0].final_cash} != "
                f"run[{i}].final_cash={runs[i].final_cash} (결정론 위반)"
            )
            assert isinstance(runs[i].final_cash, int), (
                f"run[{i}].final_cash가 int가 아님: {type(runs[i].final_cash)}"
            )
